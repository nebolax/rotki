import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional

from rotkehlchen.accounting.structures.balance import AssetBalance, Balance
from rotkehlchen.accounting.structures.types import HistoryEventSubType, HistoryEventType
from rotkehlchen.assets.asset import Asset
from rotkehlchen.chain.ethereum.contracts import EthereumContract
from rotkehlchen.chain.ethereum.defi.curve_pools import CURVE_POOLS
from rotkehlchen.chain.ethereum.modules.convex.constants import (
    CONVEX_BALANCE_ABI,
    CONVEX_POOLS,
    CPT_CONVEX,
)
from rotkehlchen.chain.ethereum.utils import multicall_specific, token_normalized_value_decimals
from rotkehlchen.db.filtering import HistoryEventFilterQuery
from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.errors.misc import BlockchainQueryError, RemoteError
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.premium.premium import Premium
from rotkehlchen.types import ChecksumEthAddress, Timestamp
from rotkehlchen.user_messages import MessagesAggregator
from rotkehlchen.utils.interfaces import EthereumModule
from rotkehlchen.utils.misc import ts_ms_to_sec
from rotkehlchen.utils.mixins.serializableenum import SerializableEnumMixin

if TYPE_CHECKING:
    from rotkehlchen.chain.ethereum.manager import EthereumManager
    from rotkehlchen.db.dbhandler import DBHandler


logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class ConvexEventType(SerializableEnumMixin):
    DEPOSIT = 1
    WITHDRAWAL = 2
    REWARD = 3


class ConvexEvent(NamedTuple):
    timestamp: Timestamp
    tx_hash: bytes
    event_type: ConvexEventType
    asset: Asset
    balance: Balance

    def serialize(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'tx_hash': self.tx_hash.hex(),
            'event_type': self.event_type.serialize(),
            'asset': self.asset.serialize(),
            'balance': self.balance.serialize(),
        }


class Convex(EthereumModule):
    def __init__(
            self,
            ethereum_manager: 'EthereumManager',
            database: 'DBHandler',
            premium: Optional[Premium],
            msg_aggregator: MessagesAggregator,
    ) -> None:
        self.ethereum_manager = ethereum_manager
        self.database = database
        self.premium = premium
        self.msg_aggregator = msg_aggregator
        self.staking_pools = {}
        for pool_addr, token_addr in CONVEX_POOLS.items():
            self.staking_pools[token_addr] = EthereumContract(address=pool_addr, abi=CONVEX_BALANCE_ABI, deployed_block=0)  # noqa: E501

    def _process_pools_data(
            self,
            lp_token_raw_amount: int,
            lp_token_address: ChecksumEthAddress,
    ) -> Optional[List[AssetBalance]]:
        staking_balances: List[AssetBalance] = []
        if lp_token_raw_amount == 0:
            return None
        lp_token_amount = token_normalized_value_decimals(
            token_amount=lp_token_raw_amount,
            token_decimals=18,
        )
        pool_tokens_base_amount = Inquirer().find_curve_pool_tokens_amount(
            lp_token_address=lp_token_address,
        )
        if pool_tokens_base_amount is None:
            return None
        for token, (base_amount, usd_price) in pool_tokens_base_amount.items():
            token_amount = base_amount * lp_token_amount
            staking_balances.append(
                AssetBalance(
                    asset=token,
                    balance=Balance(
                        amount=token_amount,
                        usd_value=token_amount * usd_price,
                    ),
                ),
            )
        return staking_balances

    def get_balances(
            self,
            addresses: List[ChecksumEthAddress],
    ) -> Dict[ChecksumEthAddress, Dict[Asset, Balance]]:
        # TODO: in current implementation we do not query all pools. Fix it.
        # This is because we need to find pool's tokens price and for this we need data about
        # curve pools which is incomplete at the moment (see curve_pools.json)
        # Full list of curve pools needed for convex is listed in constant CONVEX_POOLS.
        staking_balances: Dict[ChecksumEthAddress, Dict[Asset, Balance]] = defaultdict(lambda: defaultdict(Balance))  # noqa: E501
        tokens_to_query = self.staking_pools.keys() & CURVE_POOLS.keys()
        for lp_token_address in tokens_to_query:
            try:
                results = multicall_specific(
                    ethereum=self.ethereum_manager,
                    contract=self.staking_pools[lp_token_address],
                    method_name='balanceOf',
                    arguments=[[x] for x in addresses],
                )
            except (BlockchainQueryError, RemoteError) as e:
                log.debug(
                    f'Failed to query convex balance of addresses {addresses} for pool '
                    f'{self.staking_pools[lp_token_address]} due to {str(e)}',
                )
                continue
            for address, (lp_token_raw_amount,) in zip(addresses, results):
                lp_token_raw_amount = int(lp_token_raw_amount)
                new_balances = self._process_pools_data(
                    lp_token_raw_amount=lp_token_raw_amount,
                    lp_token_address=lp_token_address,
                )
                if new_balances is None:
                    continue
                for new_balance in new_balances:
                    staking_balances[address][new_balance.asset] += new_balance.balance

        return staking_balances

    def on_account_addition(self, address: ChecksumEthAddress) -> Optional[List[AssetBalance]]:
        """When an account is added for convex check its balances"""
        staking_balances: Dict[Asset, Balance] = defaultdict(Balance)
        tokens_to_query = self.staking_pools.keys() & CURVE_POOLS.keys()
        for lp_token_address in tokens_to_query:
            pool = self.staking_pools[lp_token_address]
            try:
                lp_token_raw_amount = self.ethereum_manager.call_contract(
                    contract_address=pool.address,
                    abi=pool.abi,
                    method_name='balanceOf',
                    arguments=[address],
                )
            except (BlockchainQueryError, RemoteError) as e:
                log.debug(
                    f'Failed to query convex balance of address {address} for pool '
                    f'{pool.address} due to {str(e)}',
                )
                continue
            lp_token_raw_amount = int(lp_token_raw_amount)
            new_balances = self._process_pools_data(
                lp_token_raw_amount=lp_token_raw_amount,
                lp_token_address=lp_token_address,
            )
            if new_balances is None:
                continue
            for new_balance in new_balances:
                staking_balances[new_balance.asset] += new_balance.balance
        # Need the conversion below to comply with other on_account_addition functions
        return [AssetBalance(asset=asset, balance=balance) for asset, balance in staking_balances.items()]  # noqa: E501

    def get_history(
            self,
            from_timestamp: Timestamp,
            to_timestamp: Timestamp,
    ) -> Dict[str, List[ConvexEvent]]:
        db_events = DBHistoryEvents(database=self.database)
        convex_events = defaultdict(list)
        with db_events.db.conn.read_ctx() as cursor:
            events_from_db = db_events.get_history_events(
                cursor, HistoryEventFilterQuery.make(
                    protocols=[CPT_CONVEX],
                    from_ts=from_timestamp,
                    to_ts=to_timestamp,
                ),
                has_premium=self.premium is not None,
            )
        for event in events_from_db:
            if (
                event.event_type == HistoryEventType.RECEIVE and
                event.event_subtype == HistoryEventSubType.REWARD
            ):
                convex_event_type = ConvexEventType.REWARD
            elif event.event_type == HistoryEventType.DEPOSIT:
                convex_event_type = ConvexEventType.DEPOSIT
            elif event.event_type == HistoryEventType.WITHDRAWAL:
                convex_event_type = ConvexEventType.WITHDRAWAL
            elif (
                event.event_type == HistoryEventType.SPEND and
                event.event_subtype in (HistoryEventSubType.FEE, HistoryEventSubType.RETURN_WRAPPED)  # noqa: E501
            ):
                continue  # We don't need to show these events on the page
            else:
                log.warning(
                    'Unknown convex type event found. Check the decoder!',
                    event_type=event.event_type,
                    event_subtype=event.event_subtype,
                    tx_hash=event.event_identifier,
                    sequence_index=event.sequence_index,
                )
                continue
            if event.location_label is None:
                log.warning(
                    'Skipping event with None location_label during querying convex history',
                    tx_hash=event.event_identifier,
                    sequence_index=event.sequence_index,
                )
                continue
            convex_events[event.location_label].append(ConvexEvent(
                timestamp=ts_ms_to_sec(event.timestamp),
                tx_hash=event.event_identifier,
                event_type=convex_event_type,
                asset=event.asset,
                balance=event.balance,
            ))
        return convex_events

    def on_account_removal(self, address: ChecksumEthAddress) -> None:
        pass

    def deactivate(self) -> None:
        pass
