import datetime
import hashlib
import hmac
import os
import re
import warnings as test_warnings
from contextlib import ExitStack
from unittest.mock import call, patch
from urllib.parse import urlencode

import pytest
import requests

from rotkehlchen.assets.asset import Asset
from rotkehlchen.assets.converters import UNSUPPORTED_BINANCE_ASSETS, asset_from_binance
from rotkehlchen.assets.exchanges_mappings.binance import WORLD_TO_BINANCE
from rotkehlchen.constants.assets import A_ADA, A_BNB, A_BTC, A_DOT, A_ETH, A_EUR, A_USDT, A_WBTC
from rotkehlchen.constants.timing import DEFAULT_TIMEOUT_TUPLE
from rotkehlchen.db.constants import BINANCE_MARKETS_KEY
from rotkehlchen.errors.asset import UnknownAsset, UnsupportedAsset
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.exchanges.binance import (
    API_TIME_INTERVAL_CONSTRAINT_TS,
    BINANCE_LAUNCH_TS,
    RETRY_AFTER_LIMIT,
    Binance,
    trade_from_binance,
)
from rotkehlchen.exchanges.data_structures import Location, Trade, TradeType
from rotkehlchen.fval import FVal
from rotkehlchen.tests.utils.constants import A_BUSD, A_LUNA, A_RDN
from rotkehlchen.tests.utils.exchanges import (
    BINANCE_DEPOSITS_HISTORY_RESPONSE,
    BINANCE_FIATBUY_RESPONSE,
    BINANCE_FIATDEPOSITS_RESPONSE,
    BINANCE_FIATSELL_RESPONSE,
    BINANCE_FIATWITHDRAWS_RESPONSE,
    BINANCE_MYTRADES_RESPONSE,
    BINANCE_WITHDRAWALS_HISTORY_RESPONSE,
    assert_binance_asset_movements_result,
    mock_binance_balance_response,
)
from rotkehlchen.tests.utils.mock import MockResponse
from rotkehlchen.types import ApiKey, ApiSecret, Timestamp
from rotkehlchen.utils.misc import ts_now_in_ms


def test_name():
    exchange = Binance('binance1', 'a', b'a', object(), object())
    assert exchange.location == Location.BINANCE
    assert exchange.name == 'binance1'


def test_trade_from_binance(function_scope_binance):
    binance = function_scope_binance
    binance_trades_list = [
        {
            'symbol': 'RDNETH',
            'id': 1,
            'orderId': 1,
            'price': FVal(0.0063213),
            'qty': FVal(5.0),
            'commission': FVal(0.005),
            'commissionAsset': 'RDN',
            'time': 1512561941000,
            'isBuyer': True,
            'isMaker': False,
            'isBestMatch': True,
        }, {
            'symbol': 'ETHUSDT',
            'id': 2,
            'orderId': 2,
            'price': FVal(481.0),
            'qty': FVal(0.505),
            'commission': FVal(0.242905),
            'commissionAsset': 'USDT',
            'time': 1531117990000,
            'isBuyer': False,
            'isMaker': True,
            'isBestMatch': True,
        }, {
            'symbol': 'BTCUSDT',
            'id': 3,
            'orderId': 3,
            'price': FVal(6376.39),
            'qty': FVal(0.051942),
            'commission': FVal(0.00005194),
            'commissionAsset': 'BTC',
            'time': 1531728338000,
            'isBuyer': True,
            'isMaker': False,
            'isBestMatch': True,
        }, {
            'symbol': 'ADAUSDT',
            'id': 4,
            'orderId': 4,
            'price': FVal(0.17442),
            'qty': FVal(285.2),
            'commission': FVal(0.00180015),
            'commissionAsset': 'BNB',
            'time': 1531871806000,
            'isBuyer': False,
            'isMaker': True,
            'isBestMatch': True,
        },
    ]
    our_expected_list = [
        Trade(
            timestamp=1512561941,
            location=Location.BINANCE,
            base_asset=A_RDN,
            quote_asset=A_ETH,
            trade_type=TradeType.BUY,
            amount=FVal(5.0),
            rate=FVal(0.0063213),
            fee=FVal(0.005),
            fee_currency=A_RDN,
            link='1',
        ),
        Trade(
            timestamp=1531117990,
            location=Location.BINANCE,
            base_asset=A_ETH,
            quote_asset=A_USDT,
            trade_type=TradeType.SELL,
            amount=FVal(0.505),
            rate=FVal(481.0),
            fee=FVal(0.242905),
            fee_currency=A_USDT,
            link='2',
        ),
        Trade(
            timestamp=1531728338,
            location=Location.BINANCE,
            base_asset=A_BTC,
            quote_asset=A_USDT,
            trade_type=TradeType.BUY,
            amount=FVal(0.051942),
            rate=FVal(6376.39),
            fee=FVal(0.00005194),
            fee_currency=A_BTC,
            link='3',
        ),
        Trade(
            timestamp=1531871806,
            location=Location.BINANCE,
            base_asset=A_ADA,
            quote_asset=A_USDT,
            trade_type=TradeType.SELL,
            amount=FVal(285.2),
            rate=FVal(0.17442),
            fee=FVal(0.00180015),
            fee_currency=A_BNB,
            link='4',
        ),
    ]

    for idx, binance_trade in enumerate(binance_trades_list):
        our_trade = trade_from_binance(binance_trade, binance.symbols_to_pair, location=Location.BINANCE)  # noqa: E501
        assert our_trade == our_expected_list[idx]
        assert isinstance(our_trade.fee_currency, Asset)


@pytest.mark.skipif(
    'CI' in os.environ,
    reason='https://twitter.com/LefterisJP/status/1598107187184037888',
)
def test_binance_assets_are_known(inquirer):  # pylint: disable=unused-argument
    unsupported_assets = set(UNSUPPORTED_BINANCE_ASSETS)
    common_items = unsupported_assets.intersection(set(WORLD_TO_BINANCE.values()))
    assert not common_items, f'Binance assets {common_items} should not be unsupported'

    exchange_data = requests.get('https://api3.binance.com/api/v3/exchangeInfo').json()
    binance_assets = set()
    for pair_symbol in exchange_data['symbols']:
        binance_assets.add(pair_symbol['baseAsset'])
        binance_assets.add(pair_symbol['quoteAsset'])

    sorted_assets = sorted(binance_assets)
    for binance_asset in sorted_assets:
        try:
            _ = asset_from_binance(binance_asset)
        except UnsupportedAsset:
            assert binance_asset in UNSUPPORTED_BINANCE_ASSETS
        except UnknownAsset as e:
            test_warnings.warn(UserWarning(
                f'Found unknown asset {e.identifier} with symbol {binance_asset} in binance. '
                f'Support for it has to be added',
            ))


def test_binance_query_balances_include_features(function_scope_binance):
    """Test that querying binance balances includes the futures wallet"""
    binance = function_scope_binance
    with patch.object(binance.session, 'get', side_effect=mock_binance_balance_response):
        balances, msg = binance.query_balances()

    assert msg == ''
    assert len(balances) == 6
    assert balances[A_BTC].amount == FVal('4723849.39208129')
    assert balances[A_ETH].amount == FVal('4763368.68006011')
    assert balances[A_BUSD].amount == FVal('7.49283144')
    assert balances[A_USDT].amount == FVal('201.01')
    assert balances[A_DOT].amount == FVal('500.55')
    assert balances[A_WBTC].amount == FVal('2.1')

    warnings = binance.msg_aggregator.consume_warnings()
    assert len(warnings) == 1
    assert 'unknown binance asset IDONTEXIST' in warnings[0]


TIMESTAMPS_RE = re.compile(r'.*&startTime\=(.*?)&endTime\=(.*?)&')


def test_binance_query_trade_history(function_scope_binance):
    """Test that turning a binance trade as returned by the server to our format works"""
    binance = function_scope_binance

    def mock_my_trades(url, **kwargs):  # pylint: disable=unused-argument
        if 'myTrades' in url:
            if 'symbol=BNBBTC' in url:
                text = BINANCE_MYTRADES_RESPONSE
            else:
                text = '[]'
        elif 'fiat/payments' in url:
            match = TIMESTAMPS_RE.search(url)
            assert match
            groups = match.groups()
            assert len(groups) == 2
            from_ts, to_ts = (int(x) for x in groups)
            if 'transactionType=0' in url:
                if from_ts < 1624529919000 < to_ts:
                    text = BINANCE_FIATBUY_RESPONSE
                else:
                    text = '[]'
            elif 'transactionType=1' in url:
                if from_ts < 1628529919000 < to_ts:
                    text = BINANCE_FIATSELL_RESPONSE
                else:
                    text = '[]'
            else:
                raise AssertionError('Unexpected binance request in test')
        else:
            raise AssertionError('Unexpected binance request in test')

        return MockResponse(200, text)

    with patch.object(binance.session, 'get', side_effect=mock_my_trades):
        trades = binance.query_trade_history(start_ts=0, end_ts=1638529919, only_cache=False)

    expected_trades = [Trade(
        timestamp=1499865549,
        location=Location.BINANCE,
        base_asset=A_BNB,
        quote_asset=A_BTC,
        trade_type=TradeType.BUY,
        amount=FVal('12'),
        rate=FVal('4.00000100'),
        fee=FVal('10.10000000'),
        fee_currency=A_BNB,
        link='28457',
    ), Trade(
        timestamp=1624529919,
        location=Location.BINANCE,
        base_asset=A_LUNA,
        quote_asset=A_EUR,
        trade_type=TradeType.BUY,
        amount=FVal('4.462'),
        rate=FVal('4.437472'),
        fee=FVal('0.2'),
        fee_currency=A_EUR,
        link='353fca443f06466db0c4dc89f94f027a',
    ), Trade(
        timestamp=1628529919,
        location=Location.BINANCE,
        base_asset=A_ETH,
        quote_asset=A_EUR,
        trade_type=TradeType.SELL,
        amount=FVal('4.462'),
        rate=FVal('4.437472'),
        fee=FVal('0.2'),
        fee_currency=A_EUR,
        link='463fca443f06466db0c4dc89f94f027a',
    )]

    assert trades == expected_trades


def test_binance_query_trade_history_unexpected_data(function_scope_binance):
    """Test that turning a binance trade that contains unexpected data is handled gracefully"""
    binance = function_scope_binance
    binance.cache_ttl_secs = 0

    def mock_my_trades(url, **kwargs):  # pylint: disable=unused-argument
        if 'symbol=BNBBTC' in url or 'symbol=doesnotexist' in url:
            text = BINANCE_MYTRADES_RESPONSE
        else:
            text = '[]'

        return MockResponse(200, text)

    def query_binance_and_test(
            input_trade_str,
            expected_warnings_num,
            expected_errors_num,
            warning_str_test=None,
            error_str_test=None,
            query_specific_markets=None,
    ):
        patch_get = patch.object(binance.session, 'get', side_effect=mock_my_trades)
        patch_response = patch(
            'rotkehlchen.tests.exchanges.test_binance.BINANCE_MYTRADES_RESPONSE',
            new=input_trade_str,
        )
        binance.selected_pairs = query_specific_markets
        with patch_get, patch_response:
            trades, _ = binance.query_online_trade_history(
                start_ts=0,
                end_ts=1564301134,
            )

        assert len(trades) == 0
        errors = binance.msg_aggregator.consume_errors()
        warnings = binance.msg_aggregator.consume_warnings()
        assert len(errors) == expected_errors_num
        assert len(warnings) == expected_warnings_num
        if warning_str_test:
            assert warning_str_test in warnings[0]
        if error_str_test:
            assert error_str_test in errors[0]

    input_str = BINANCE_MYTRADES_RESPONSE.replace(
        '"qty": "12.00000000"',
        '"qty": "dsadsad"',
    )
    query_binance_and_test(input_str, expected_warnings_num=0, expected_errors_num=1)

    input_str = BINANCE_MYTRADES_RESPONSE.replace(
        '"price": "4.00000100"',
        '"price": null',
    )
    query_binance_and_test(input_str, expected_warnings_num=0, expected_errors_num=1)

    input_str = BINANCE_MYTRADES_RESPONSE.replace(
        '"symbol": "BNBBTC"',
        '"symbol": "nonexistingmarket"',
    )
    query_binance_and_test(
        input_str,
        expected_warnings_num=0,
        expected_errors_num=0,
        query_specific_markets=['doesnotexist'],
    )

    input_str = BINANCE_MYTRADES_RESPONSE.replace(
        '"time": 1499865549590',
        '"time": "sadsad"',
    )
    query_binance_and_test(input_str, expected_warnings_num=0, expected_errors_num=1)

    # Delete an entry
    input_str = BINANCE_MYTRADES_RESPONSE.replace('"isBuyer": true,', '')
    query_binance_and_test(input_str, expected_warnings_num=0, expected_errors_num=1)

    input_str = BINANCE_MYTRADES_RESPONSE.replace(
        '"commission": "10.10000000"',
        '"commission": "fdfdfdsf"',
    )
    query_binance_and_test(input_str, expected_warnings_num=0, expected_errors_num=1)

    # unsupported fee currency
    input_str = BINANCE_MYTRADES_RESPONSE.replace(
        '"commissionAsset": "BNB"',
        '"commissionAsset": "BTCB"',
    )
    query_binance_and_test(
        input_str,
        expected_warnings_num=1,
        expected_errors_num=0,
        warning_str_test='Found binance trade with unsupported asset BTCB',
    )

    # unknown fee currency
    input_str = BINANCE_MYTRADES_RESPONSE.replace(
        '"commissionAsset": "BNB"',
        '"commissionAsset": "DSDSDS"',
    )
    query_binance_and_test(
        input_str,
        expected_warnings_num=1,
        expected_errors_num=0,
        warning_str_test='Found binance trade with unknown asset DSDSDS',
    )


def test_binance_query_deposits_withdrawals(function_scope_binance):
    """Test the happy case of binance deposit withdrawal query

    NB: set `start_ts` and `end_ts` with a difference less than 90 days to
    prevent requesting with a time delta.
    """
    start_ts = 1508022000  # 2017-10-15
    end_ts = 1636400907
    binance = function_scope_binance

    def mock_get_deposit_withdrawal(url, **kwargs):  # pylint: disable=unused-argument
        match = TIMESTAMPS_RE.search(url)
        assert match
        groups = match.groups()
        assert len(groups) == 2
        from_ts, to_ts = (int(x) for x in groups)
        if 'capital/deposit' in url:
            if from_ts >= 1508022000000 and to_ts <= 1515797999999:
                response_str = BINANCE_DEPOSITS_HISTORY_RESPONSE
            else:
                response_str = '[]'
        elif 'capital/withdraw' in url:
            if from_ts <= 1508198532000 <= to_ts:
                response_str = BINANCE_WITHDRAWALS_HISTORY_RESPONSE
            else:
                response_str = '[]'
        elif 'fiat/orders' in url:
            from_ts, to_ts = (int(x) for x in groups)
            if 'transactionType=0' in url:
                if from_ts < 1626144956000 < to_ts:
                    response_str = BINANCE_FIATDEPOSITS_RESPONSE
                else:
                    response_str = '[]'
            elif 'transactionType=1' in url:
                if from_ts < 1636144956000 < to_ts:
                    response_str = BINANCE_FIATWITHDRAWS_RESPONSE
                else:
                    response_str = '[]'
            else:
                raise AssertionError('Unexpected binance request in test')
        else:
            raise AssertionError('Unexpected binance request in test')

        return MockResponse(200, response_str)

    with patch.object(binance.session, 'get', side_effect=mock_get_deposit_withdrawal):
        movements = binance.query_online_deposits_withdrawals(
            start_ts=Timestamp(start_ts),
            end_ts=Timestamp(end_ts),
        )

    errors = binance.msg_aggregator.consume_errors()
    warnings = binance.msg_aggregator.consume_warnings()
    assert len(errors) == 0
    assert len(warnings) == 0
    assert_binance_asset_movements_result(
        movements=movements,
        location=Location.BINANCE,
        got_fiat=True,
    )


def test_binance_query_deposits_withdrawals_unexpected_data(function_scope_binance):
    """Test that we handle unexpected deposit withdrawal query data gracefully

    NB: set `start_ts` and `end_ts` with a difference less than 90 days to
    prevent requesting with a time delta.
    """
    start_ts = 1508022000  # 2017-10-15
    end_ts = 1508540400  # 2017-10-21 (less than 90 days since `start_ts`)
    binance = function_scope_binance

    def mock_binance_and_query(deposits, withdrawals, expected_warnings_num, expected_errors_num):

        def mock_get_deposit_withdrawal(url, **kwargs):  # pylint: disable=unused-argument
            if 'deposit' in url:
                response_str = deposits
            else:
                response_str = withdrawals

            return MockResponse(200, response_str)

        with patch.object(binance.session, 'get', side_effect=mock_get_deposit_withdrawal):
            movements = binance.query_online_deposits_withdrawals(
                start_ts=Timestamp(start_ts),
                end_ts=Timestamp(end_ts),
            )

        if expected_errors_num == 0 and expected_warnings_num == 0:
            assert len(movements) == 1
        else:
            assert len(movements) == 0
            warnings = binance.msg_aggregator.consume_warnings()
            assert len(warnings) == expected_warnings_num
            errors = binance.msg_aggregator.consume_errors()
            assert len(errors) == expected_errors_num

    def check_permutations_of_input_invalid_data(deposits, withdrawals):
        # First make sure it works with normal data
        mock_binance_and_query(
            deposits,
            withdrawals,
            expected_warnings_num=0,
            expected_errors_num=0,
        )
        testing_deposits = 'amount' in deposits

        # From here and on test unexpected data
        # invalid timestamp
        if testing_deposits:
            new_deposits = deposits.replace('1508198532000', '"dasdd"')
            new_withdrawals = withdrawals
        else:
            new_deposits = deposits
            new_withdrawals = withdrawals.replace('"2017-10-17 00:02:12"', '"dasdd"')
        mock_binance_and_query(
            new_deposits,
            new_withdrawals,
            expected_warnings_num=0,
            expected_errors_num=1,
        )

        # invalid asset
        if testing_deposits:
            new_deposits = deposits.replace('"ETH"', '[]')
            new_withdrawals = withdrawals
        else:
            new_deposits = deposits
            new_withdrawals = withdrawals.replace('"ETH"', '[]')
        mock_binance_and_query(
            new_deposits,
            new_withdrawals,
            expected_warnings_num=0,
            expected_errors_num=1,
        )

        # Unknown asset
        if testing_deposits:
            new_deposits = deposits.replace('"ETH"', '"dasdsDSDSAD"')
            new_withdrawals = withdrawals
        else:
            new_deposits = deposits
            new_withdrawals = withdrawals.replace('"ETH"', '"dasdsDSDSAD"')
        mock_binance_and_query(
            new_deposits,
            new_withdrawals,
            expected_warnings_num=1,
            expected_errors_num=0,
        )

        # Unsupported Asset
        if testing_deposits:
            new_deposits = deposits.replace('"ETH"', '"BTCB"')
            new_withdrawals = withdrawals
        else:
            new_deposits = deposits
            new_withdrawals = withdrawals.replace('"ETH"', '"BTCB"')
        mock_binance_and_query(
            new_deposits,
            new_withdrawals,
            expected_warnings_num=1,
            expected_errors_num=0,
        )

        # Invalid amount
        if testing_deposits:
            new_deposits = deposits.replace('0.04670582', 'null')
            new_withdrawals = withdrawals
        else:
            new_deposits = deposits
            new_withdrawals = withdrawals.replace('0.04670582', 'null')
        mock_binance_and_query(
            new_deposits,
            new_withdrawals,
            expected_warnings_num=0,
            expected_errors_num=1,
        )

        # Missing Key Error
        if testing_deposits:
            new_deposits = deposits.replace('"amount": 0.04670582,', '')
            new_withdrawals = withdrawals
        else:
            new_deposits = deposits
            new_withdrawals = withdrawals.replace('"amount": 0.04670582,', '')
        mock_binance_and_query(
            new_deposits,
            new_withdrawals,
            expected_warnings_num=0,
            expected_errors_num=1,
        )

    # To make the test easy to write the values for deposit/withdrawal attributes
    # are the same in the two examples below
    empty_deposits = '[]'
    empty_withdrawals = '[]'
    input_withdrawals = """[{
        "id":"7213fea8e94b4a5593d507237e5a555b",
        "amount": 0.04670582,
        "transactionFee": 0.01,
        "address": "0x6915f16f8791d0a1cc2bf47c13a6b2a92000504b",
        "coin": "ETH",
        "txId": "0xdf33b22bdb2b28b1f75ccd201a4a4m6e7g83jy5fc5d5a9d1340961598cfcb0a1",
        "applyTime": "2017-10-17 00:02:12",
        "status": 4
        }]"""
    check_permutations_of_input_invalid_data(
        deposits=empty_deposits,
        withdrawals=input_withdrawals,
    )

    input_deposits = """[{
        "insertTime": 1508198532000,
        "amount": 0.04670582,
        "coin": "ETH",
        "address": "0x6915f16f8791d0a1cc2bf47c13a6b2a92000504b",
        "txId": "0xdf33b22bdb2b28b1f75ccd201a4a4m6e7g83jy5fc5d5a9d1340961598cfcb0a1",
        "status": 1
        }]"""
    check_permutations_of_input_invalid_data(
        deposits=input_deposits,
        withdrawals=empty_withdrawals,
    )


def test_binance_query_deposits_withdrawals_gte_90_days(function_scope_binance):
    """Test the not so happy case of binance deposit withdrawal query

    From `start_ts` to `end_ts` there is a difference gte 90 days, which forces
    to request using a time delta (from API_TIME_INTERVAL_CONSTRAINT_TS). As
    the `mock_get_deposit_withdrawal()` results are the same as in
    `test_binance_query_deposits_withdrawals`, we only assert the number of
    movements.

    NB: this test implementation must mock 8 requests instead of 4.
    """
    start_ts = 0  # Defaults to BINANCE_LAUNCH_TS
    end_ts = BINANCE_LAUNCH_TS + API_TIME_INTERVAL_CONSTRAINT_TS  # eq 90 days after
    binance = function_scope_binance

    def get_time_delta_deposit_result():
        results = [
            BINANCE_DEPOSITS_HISTORY_RESPONSE,
            '[]',
        ]
        yield from results

    def get_time_delta_withdraw_result():
        results = [
            '[]',
            BINANCE_WITHDRAWALS_HISTORY_RESPONSE,
        ]
        yield from results

    def get_fiat_deposit_result():
        results = [
            '[]',
            BINANCE_FIATDEPOSITS_RESPONSE,
        ]
        yield from results

    def get_fiat_withdraw_result():
        results = [
            BINANCE_FIATWITHDRAWS_RESPONSE,
            '[]',
        ]
        yield from results

    def mock_get_deposit_withdrawal(url, **kwargs):  # pylint: disable=unused-argument
        if 'capital/deposit' in url:
            response_str = next(get_deposit_result)
        elif 'capital/withdraw' in url:
            response_str = next(get_withdraw_result)
        elif 'fiat/orders' in url:
            if 'transactionType=0' in url:
                response_str = next(get_fiat_deposit_result)
            elif 'transactionType=1' in url:
                response_str = next(get_fiat_withdraw_result)
            else:
                raise AssertionError('Unexpected binance request in test')

        else:
            raise AssertionError('Unexpected binance request in test')

        return MockResponse(200, response_str)

    get_deposit_result = get_time_delta_deposit_result()
    get_withdraw_result = get_time_delta_withdraw_result()
    get_fiat_deposit_result = get_fiat_deposit_result()
    get_fiat_withdraw_result = get_fiat_withdraw_result()

    with patch.object(binance.session, 'get', side_effect=mock_get_deposit_withdrawal):
        movements = binance.query_online_deposits_withdrawals(
            start_ts=Timestamp(start_ts),
            end_ts=Timestamp(end_ts),
        )

    errors = binance.msg_aggregator.consume_errors()
    warnings = binance.msg_aggregator.consume_warnings()
    assert len(errors) == 0
    assert len(warnings) == 0

    assert len(movements) == 6


@pytest.mark.freeze_time(datetime.datetime(2020, 11, 24, 3, 14, 15, tzinfo=datetime.timezone.utc))
def test_api_query_list_calls_with_time_delta(function_scope_binance):
    """Test the `api_query_list()` arguments when deposit/withdraw history
    requests involve a time delta.

    From `start_ts` to `end_ts` there is a difference gte 90 days, which forces
    to request using a time delta (from API_TIME_INTERVAL_CONSTRAINT_TS).
    """
    now_ts_ms = int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp()) * 1000
    start_ts = 0  # Defaults to BINANCE_LAUNCH_TS
    end_ts = BINANCE_LAUNCH_TS + API_TIME_INTERVAL_CONSTRAINT_TS  # eq 90 days after
    expected_calls = [
        call(
            'sapi',
            'capital/deposit/hisrec',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1500001200000,
                'endTime': 1507777199999,
            },
        ),
        call(
            'sapi',
            'capital/deposit/hisrec',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1507777200000,
                'endTime': 1507777200000,
            },
        ),
        call(
            'sapi',
            'capital/withdraw/history',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1500001200000,
                'endTime': 1507777199999,
            },
        ),
        call(
            'sapi',
            'capital/withdraw/history',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1507777200000,
                'endTime': 1507777200000,
            },
        ),
        call(
            'sapi',
            'fiat/orders',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1500001200000,
                'endTime': 1507777199999,
                'transactionType': 0,
            },
        ),
        call(
            'sapi',
            'fiat/orders',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1507777200000,
                'endTime': 1507777200000,
                'transactionType': 0,
            },
        ),
        call(
            'sapi',
            'fiat/orders',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1500001200000,
                'endTime': 1507777199999,
                'transactionType': 1,
            },
        ),
        call(
            'sapi',
            'fiat/orders',
            options={
                'timestamp': now_ts_ms,
                'startTime': 1507777200000,
                'endTime': 1507777200000,
                'transactionType': 1,
            },
        ),
    ]
    binance = function_scope_binance

    with patch.object(binance, 'api_query_list') as mock_api_query_list:
        binance.query_online_deposits_withdrawals(
            start_ts=Timestamp(start_ts),
            end_ts=Timestamp(end_ts),
        )
        assert mock_api_query_list.call_args_list == expected_calls


@pytest.mark.freeze_time(datetime.datetime(2020, 11, 24, 3, 14, 15, tzinfo=datetime.timezone.utc))
def test_api_query_retry_on_status_code_429(function_scope_binance):
    """Test when Binance API returns 429 and the request is retried, the
    signature is not polluted by any attribute from the previous call.

    It also tests getting the `retry-after` seconds to backoff from the
    response header.

    NB: basically remove `call_options['signature']`.
    """
    binance = function_scope_binance
    offset_ms = 1000
    call_options = {
        'fromId': 0,
        'limit': 1000,
        'symbol': 'BUSDUSDT',
        'recvWindow': 10000,
        'timestamp': str(ts_now_in_ms() + offset_ms),
    }
    signature = hmac.new(
        binance.secret,
        urlencode(call_options).encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    call_options['signature'] = signature
    base_url = 'https://api.binance.com/api/v3/myTrades?'
    exp_request_url = base_url + urlencode(call_options)

    # NB: all calls must have the same signature (time frozen)
    expected_calls = [
        call(exp_request_url, timeout=DEFAULT_TIMEOUT_TUPLE),
        call(exp_request_url, timeout=DEFAULT_TIMEOUT_TUPLE),
        call(exp_request_url, timeout=DEFAULT_TIMEOUT_TUPLE),
    ]

    def get_mocked_response():
        responses = [
            MockResponse(429, '[]', headers={'retry-after': '1'}),
            MockResponse(418, '[]', headers={'retry-after': '5'}),
            MockResponse(418, '[]', headers={'retry-after': str(RETRY_AFTER_LIMIT + 1)}),
        ]
        yield from responses

    def mock_response(url, timeout):  # pylint: disable=unused-argument
        return next(get_response)

    get_response = get_mocked_response()
    offset_ms_patch = patch.object(binance, 'offset_ms', new=1000)
    binance_patch = patch.object(binance.session, 'get', side_effect=mock_response)

    with ExitStack() as stack:
        stack.enter_context(offset_ms_patch)
        binance_mock_get = stack.enter_context(binance_patch)
        with pytest.raises(RemoteError) as e:
            binance.api_query(
                api_type='api',
                method='myTrades',
                options={
                    'fromId': 0,
                    'limit': 1000,
                    'symbol': 'BUSDUSDT',
                },
            )
    assert 'myTrades failed with HTTP status code: 418' in str(e.value)
    assert binance_mock_get.call_args_list == expected_calls


def test_binance_query_trade_history_custom_markets(function_scope_binance):
    """Test that custom pairs are queried correctly"""
    binance_api_key = ApiKey('binance_api_key')
    binance_api_secret = ApiSecret(b'binance_api_secret')
    function_scope_binance.db.add_exchange(
        name='binance',
        location=Location.BINANCE,
        api_key=binance_api_key,
        api_secret=binance_api_secret,
    )
    binance = function_scope_binance

    markets = ['ETHBTC', 'BNBBTC', 'BTCUSDC']
    binance.edit_exchange_extras({BINANCE_MARKETS_KEY: markets})
    count = 0
    p = re.compile(r'symbol=[A-Z]*')
    seen = set()

    def mock_my_trades(url, timeout):  # pylint: disable=unused-argument
        nonlocal count
        if '/fiat/payments' not in url:
            count += 1
            market = p.search(url).group()[7:]
            assert market in markets and market not in seen
            seen.add(market)
        text = '[]'
        return MockResponse(200, text)

    with patch.object(binance.session, 'get', side_effect=mock_my_trades):
        binance.query_trade_history(start_ts=0, end_ts=1564301134, only_cache=False)

    assert count == len(markets)
