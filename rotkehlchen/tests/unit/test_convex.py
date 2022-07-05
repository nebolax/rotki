from typing import Any, List, Tuple
from unittest.mock import patch

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.asset import EthereumToken
from rotkehlchen.chain.ethereum.contracts import EthereumContract
from rotkehlchen.chain.ethereum.modules import Convex
from rotkehlchen.chain.ethereum.types import string_to_ethereum_address
from rotkehlchen.constants.assets import A_CRV_3CRV, A_DAI, A_USDC, A_USDT
from rotkehlchen.fval import FVal
from rotkehlchen.types import ChecksumEthAddress
from rotkehlchen.user_messages import MessagesAggregator


def test_convex_balances(database, ethereum_manager, inquirer):
    """The test checks that convex pools balances are calculated properly.
    Tested cases:
    - pool with 2 tokens
    - pool with 3 tokens
    - various balances of each token in a pool (e.g. the portion of a token in a pool)
    - various staked amounts
    - 2 addresses staking in the same pool
    - single address staking in 2 pools that have mutual tokens (tests that token balances are summed)
    """  # noqa: E501
    def mock_convex_multicall(contract: EthereumContract, **kwargs: Any) -> Any:  # pylint: disable=unused-argument  # noqa: E501
        if contract.address == '0x689440f2Ff927E1f24c72F1087E1FAF471eCe1c8':
            return [(1e18,), (0,), (0,)]
        if contract.address == '0xB900EF131301B307dB5eFcbed9DBb50A3e209B2e':
            return [(0,), (1e18,), (0,)]
        if contract.address == '0x4a2631d090e8b40bBDe245e687BF09e5e534A239':
            return [(2e18,), (1e18,), (0,)]
        raise AssertionError('Should never happen')

    convex_multicall_patch = patch(
        'rotkehlchen.chain.ethereum.modules.convex.convex.multicall_specific',
        new=mock_convex_multicall,
    )

    def mock_inquirer_multicall(
        calls: List[Tuple[ChecksumEthAddress, str]],  # pylint: disable=unused-argument
        **kwargs: Any,
    ) -> List[Tuple[bool, bytes]]:
        if calls[0][0] == '0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7':
            return [
                (True, int(1e12).to_bytes(length=32, byteorder='big')),
                (True, int(1).to_bytes(length=32, byteorder='big')),
                (True, int(1).to_bytes(length=32, byteorder='big')),
            ]
        if calls[0][0] == '0xd632f22692FaC7611d2AA1C0D552930D43CAEd3B':
            return [
                (True, int(4).to_bytes(length=32, byteorder='big')),
                (True, int(8).to_bytes(length=32, byteorder='big')),
            ]
        if calls[0][0] == '0x0f9cb53Ebe405d49A0bbdBD291A65Ff571bC83e1':
            return [
                (True, int(1).to_bytes(length=32, byteorder='big')),
                (True, int(3).to_bytes(length=32, byteorder='big')),
            ]
        raise AssertionError('Should never happen')

    inquirer_multicall_patch = patch(
        'rotkehlchen.inquirer.multicall_2',
        new=mock_inquirer_multicall,
    )

    msg_aggregator = MessagesAggregator()
    inquirer.inject_ethereum(ethereum_manager)

    addr1 = string_to_ethereum_address('0x331174A9067e864A61B2F87861CCf006eD3bC95D')
    addr2 = string_to_ethereum_address('0xC49Eb99c132795F74b3d6f71B2374dC35015d473')
    user_addresses = [addr1, addr2]

    with convex_multicall_patch, inquirer_multicall_patch:
        convex = Convex(
            database=database,
            ethereum_manager=ethereum_manager,
            premium=None,
            msg_aggregator=msg_aggregator,
        )
        found_balances = convex.get_balances(addresses=user_addresses)

    expected_balances = {
        addr1: {
            EthereumToken('0x674C6Ad92Fd080e4004b2312b45f796a192D27a0'): Balance(  # USDN token
                amount=FVal(0.5),
                usd_value=FVal(0.75),
            ),
            A_CRV_3CRV: Balance(amount=FVal(1.5), usd_value=FVal(2.25)),
            A_DAI: Balance(amount=FVal('0.3333333333333333333333333333'), usd_value=FVal(0.5)),
            A_USDC: Balance(amount=FVal('0.3333333333333333333333333333'), usd_value=FVal(0.5)),
            A_USDT: Balance(amount=FVal('0.3333333333333333333333333333'), usd_value=FVal(0.5)),
        }, addr2: {
            EthereumToken('0x674C6Ad92Fd080e4004b2312b45f796a192D27a0'): Balance(  # USDN token
                amount=FVal(0.25),
                usd_value=FVal(0.375),
            ),
            A_CRV_3CRV: Balance(
                amount=FVal('1.416666666666666666666666667'),
                usd_value=FVal(2.125),
            ),
            EthereumToken('0x853d955aCEf822Db058eb8505911ED77F175b99e'): Balance(  # FRAX token
                amount=FVal('0.3333333333333333333333333333'),
                usd_value=FVal(0.5),
            ),
        },
    }
    assert found_balances == expected_balances
