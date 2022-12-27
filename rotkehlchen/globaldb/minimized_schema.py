# This file contains minimized db schema and it should not be touched manually but only generated by tools/scripts/generate_minimized_db_schema.py
# Created at 2022-12-28 17:56:37 UTC with rotki version 1.26.3.dev371+g59f0477a8 by yabirgb
MINIMIZED_GLOBAL_DB_SCHEMA = {
    'token_kinds': 'token_kindCHAR(1)PRIMARYKEYNOTNULL,seqINTEGERUNIQUE',
    'underlying_tokens_list': 'identifierTEXTNOTNULL,weightTEXTNOTNULL,parent_token_entryTEXTNOTNULL,FOREIGNKEY(parent_token_entry)REFERENCESevm_tokens(identifier)ONDELETECASCADEONUPDATECASCADEFOREIGNKEY(identifier)REFERENCESevm_tokens(identifier)ONUPDATECASCADEONDELETECASCADEPRIMARYKEY(identifier,parent_token_entry)',
    'settings': 'nameVARCHAR[24]NOTNULLPRIMARYKEY,valueTEXT',
    'asset_types': 'typeCHAR(1)PRIMARYKEYNOTNULL,seqINTEGERUNIQUE',
    'assets': 'identifierTEXTPRIMARYKEYNOTNULLCOLLATENOCASE,nameTEXT,typeCHAR(1)NOTNULLDEFAULT("A")REFERENCESasset_types(type)',
    'evm_tokens': 'identifierTEXTPRIMARYKEYNOTNULLCOLLATENOCASE,token_kindCHAR(1)NOTNULLDEFAULT("A")REFERENCEStoken_kinds(token_kind),chainINTEGERNOTNULL,addressVARCHAR[42]NOTNULL,decimalsINTEGER,protocolTEXT,FOREIGNKEY(identifier)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE',
    'multiasset_mappings': 'collection_idINTEGERNOTNULL,assetTEXTNOTNULL,FOREIGNKEY(collection_id)REFERENCESasset_collections(id)ONUPDATECASCADEONDELETECASCADE,FOREIGNKEY(asset)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE',
    'common_asset_details': 'identifierTEXTPRIMARYKEYNOTNULLCOLLATENOCASE,symbolTEXT,coingeckoTEXT,cryptocompareTEXT,forkedTEXT,startedINTEGER,swapped_forTEXT,FOREIGNKEY(forked)REFERENCESassets(identifier)ONUPDATECASCADEONDELETESETNULL,FOREIGNKEY(identifier)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE,FOREIGNKEY(swapped_for)REFERENCESassets(identifier)ONUPDATECASCADEONDELETESETNULL',
    'user_owned_assets': 'asset_idVARCHAR[24]NOTNULLPRIMARYKEY,FOREIGNKEY(asset_id)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE',
    'price_history_source_types': 'typeCHAR(1)PRIMARYKEYNOTNULL,seqINTEGERUNIQUE',
    'price_history': 'from_assetTEXTNOTNULLCOLLATENOCASE,to_assetTEXTNOTNULLCOLLATENOCASE,source_typeCHAR(1)NOTNULLDEFAULT("A")REFERENCESprice_history_source_types(type),timestampINTEGERNOTNULL,priceTEXTNOTNULL,FOREIGNKEY(from_asset)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE,FOREIGNKEY(to_asset)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE,PRIMARYKEY(from_asset,to_asset,source_type,timestamp)',
    'binance_pairs': 'pairTEXTNOTNULL,base_assetTEXTNOTNULL,quote_assetTEXTNOTNULL,locationTEXTNOTNULL,FOREIGNKEY(base_asset)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE,FOREIGNKEY(quote_asset)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE,PRIMARYKEY(pair,location)',
    'address_book': 'addressTEXTNOTNULL,blockchainTEXT,nameTEXTNOTNULL,PRIMARYKEY(address,blockchain)',
    'custom_assets': 'identifierTEXTNOTNULLPRIMARYKEY,notesTEXT,typeTEXTNOTNULLCOLLATENOCASE,FOREIGNKEY(identifier)REFERENCESassets(identifier)ONUPDATECASCADEONDELETECASCADE',
    'asset_collections': 'idINTEGERPRIMARYKEY,nameTEXTNOTNULL,symbolTEXTNOTNULL',
    'general_cache': 'keyTEXTNOTNULL,valueTEXTNOTNULL,last_queried_tsINTEGERNOTNULL,PRIMARYKEY(key,value)',
    'contract_abi': 'idINTEGERNOTNULLPRIMARYKEY,valueTEXTNOTNULL,nameTEXT',
    'contract_data': 'addressVARCHAR[42]NOTNULL,chain_idINTEGERNOTNULL,nameTEXT,abiINTEGERNOTNULL,deployed_blockINTEGER,FOREIGNKEY(abi)REFERENCEScontract_abi(id)ONUPDATECASCADEONDELETESETNULL,PRIMARYKEY(address,chain_id)',
}
