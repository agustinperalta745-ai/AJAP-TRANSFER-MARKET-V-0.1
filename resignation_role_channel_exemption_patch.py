"""Allow Staff resignation-role decision buttons outside #mercado-de-pases.

The market channel gate correctly blocks normal market components outside the
configured interactive channel, but Staff decisions about a resigned DT are
posted in the Staff/report channel. Their buttons therefore need an explicit
component exemption, just like vacancy-admin decisions.
"""

import market_usage_channel_patch as market_usage

PREFIX = "ajap:resign-role:"

if PREFIX not in market_usage.EXEMPT_COMPONENT_PREFIXES:
    market_usage.EXEMPT_COMPONENT_PREFIXES = (
        *market_usage.EXEMPT_COMPONENT_PREFIXES,
        PREFIX,
    )

print("AJAP renuncia Staff: botones Mantener/Quitar exentos del canal único de mercado")
