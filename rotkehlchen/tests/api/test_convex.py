import pytest
import requests

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.accounting.structures.base import HistoryBaseEntry
from rotkehlchen.accounting.structures.types import HistoryEventSubType, HistoryEventType
from rotkehlchen.chain.ethereum.modules.convex.constants import CPT_CONVEX
from rotkehlchen.chain.ethereum.types import string_to_ethereum_address
from rotkehlchen.constants import ONE
from rotkehlchen.constants.assets import A_ETH
from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.tests.utils.api import api_url_for, assert_proper_response_with_result
from rotkehlchen.types import Location, TimestampMS

CONVEX_TEST_ADDR = string_to_ethereum_address('0x0633F1692Dab82F6F253eF571C769861CF90ecb6')


@pytest.mark.parametrize('ethereum_accounts', [[CONVEX_TEST_ADDR]])
@pytest.mark.parametrize('ethereum_modules', [['convex']])
@pytest.mark.parametrize('start_with_valid_premium', [True])
def test_get_history(
        rotkehlchen_api_server,
):
    db = rotkehlchen_api_server.rest_api.rotkehlchen.data.db
    dbevents = DBHistoryEvents(database=db)
    event = HistoryBaseEntry(
        event_identifier=b'\01',
        sequence_index=1,
        timestamp=TimestampMS(0),
        location=Location.BLOCKCHAIN,
        asset=A_ETH,
        balance=Balance(amount=ONE),
        location_label=CONVEX_TEST_ADDR,
        event_type=HistoryEventType.RECEIVE,
        event_subtype=HistoryEventSubType.REWARD,
        counterparty=CPT_CONVEX,
    )
    with db.user_write() as cursor:
        dbevents.add_history_event(cursor, event)
    response = requests.get(
        api_url_for(rotkehlchen_api_server, 'convexhistoryresource'),
    )
    result = assert_proper_response_with_result(response)
    expected_result = {
        '0x0633F1692Dab82F6F253eF571C769861CF90ecb6': [
            {
                'timestamp': 0,
                'tx_hash': '01',
                'event_type': 'reward',
                'asset': 'ETH',
                'balance': {
                    'amount': '1',
                    'usd_value': '0',
                },
            },
        ],
    }
    assert result == expected_result
