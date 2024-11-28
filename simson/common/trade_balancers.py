import sys


def balance_by_extrenum(trade, by: str, inplace=False):
    global_imports = trade.imports.sum_nda_over('r')
    global_exports = trade.exports.sum_nda_over('r')

    if by == 'maximum':
        reference_trade = global_imports.maximum(global_exports)
    elif by == 'minimum':
        reference_trade = global_imports.minimum(global_exports)
    elif by == 'imports':
        reference_trade = global_imports
    elif by == 'exports':
        reference_trade = global_exports
    else:
        raise ValueError(f"Extrenum {by} not recognized. Must be one of "
                         f"'maximum', 'minimum', 'imports' or 'exports'.")

    import_factor = reference_trade / global_imports.maximum(sys.float_info.epsilon)
    export_factor = reference_trade / global_exports.maximum(sys.float_info.epsilon)

    if not inplace:
        trade = trade.copy()

    trade.imports = trade.imports * import_factor
    trade.exports = trade.exports * export_factor

    return trade


def balance_by_scaling(trade, inplace=False):
    net_trade = trade.imports - trade.exports
    global_net_trade = net_trade.sum_nda_over('r')
    global_absolute_net_trade = net_trade.abs().sum_nda_over('r')

    # avoid division by zero, net_trade will be zero when global absolute net trade is zero anyways
    global_absolute_net_trade = global_absolute_net_trade.maximum(sys.float_info.epsilon)

    new_net_trade = net_trade * (1 - net_trade.sign() * global_net_trade / global_absolute_net_trade)

    if not inplace:
        trade = trade.copy()

    trade.imports = new_net_trade.maximum(0)
    trade.exports = new_net_trade.minimum(0).abs()

    return trade
