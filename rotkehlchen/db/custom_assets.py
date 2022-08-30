from typing import TYPE_CHECKING, Optional

from rotkehlchen.assets.asset import CustomAsset
from rotkehlchen.assets.types import AssetType
from rotkehlchen.errors.misc import InputError

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.db.drivers.gevent import DBCursor


class DBCustomAssets:

    def __init__(self, db_handler: 'DBHandler') -> None:
        self.db = db_handler

    def search_custom_assets(
            self,
            identifier: Optional[str],
            name: Optional[str],
            symbol: Optional[str],
            notes: Optional[str],
            custom_asset_type: Optional[str],
    ) -> None:
        # TODO: switch to db query
        query = 'SELECT identifier, name, symbol, notes, type FROM custom_assets'
        filters, bindings = [], []
        if identifier is not None:
            filters.append('identifier=?')
            bindings.append(identifier)
        if name is not None:
            filters.append('name=?')
            bindings.append(name)
        if symbol is not None:
            filters.append('symbol=?')
            bindings.append(symbol)
        if notes is not None:
            filters.append('notes=?')
            bindings.append(notes)
        if custom_asset_type is not None:
            filters.append('type=?')
            bindings.append(custom_asset_type)

        if len(filters) > 0:
            query += ' WHERE '
            query += ' AND '.join(filters)

        with self.db.conn.read_ctx() as read_cursor:
            read_cursor.execute(query, bindings)

    def add_custom_asset(self, write_cursor: 'DBCursor', custom_asset: CustomAsset) -> None:
        """Add custom new custom asset into `assets` and `custom_assets` table.
        May raise:
        -InputError if this asset already exists"""
        write_cursor.execute(
            'INSERT INTO assets(identifier, type) VALUES (?, ?)',
            (custom_asset.identifier, AssetType.CUSTOM_ASSET,)
        )
        write_cursor.execute('INSERT INTO custom_assets')

    def edit_custom_asset(self, write_cursor: 'DBCursor', custom_asset: CustomAsset) -> None:
        write_cursor.execute(
            'UPDATE custom_assets SET name=? symbol=? notes=? type=? WHERE identifier=?',
            (
                custom_asset.name,
                custom_asset.symbol,
                custom_asset.notes,
                custom_asset.custom_asset_type,
                custom_asset.identifier,
            ),
        )
        if write_cursor.rowcount != 1:
            raise InputError(
                f'Tried to edit custom asset with id {custom_asset.identifier} and name '
                f'{custom_asset.name} but it was not found',
            )

    def delete_custom_asset(self, write_cursor: 'DBCursor', identifier: CustomAsset) -> None:
        # TODO: Think about how to delete a custom asset (call globladb method here / on some higher level of abstraction)
        ...
