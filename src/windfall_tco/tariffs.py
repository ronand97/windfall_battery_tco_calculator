"""Shipped tariff presets.

Rates here are *illustrative defaults* — the real Octopus numbers change
monthly (and vary by region). Users should edit them in-app to match their
current contract before relying on the computed savings.
"""

from datetime import time

from .data_models import Tariff, TariffBand

# Octopus Cosy: four cheap-rate windows plus a peak evening window.
#   00:00-04:00 standard, 04:00-07:00 cheap, 07:00-13:00 standard,
#   13:00-16:00 cheap, 16:00-19:00 peak, 19:00-22:00 standard,
#   22:00-00:00 cheap.
# Illustrative rates: cheap 12.0p, standard 27.0p, peak 42.0p per kWh.
OCTOPUS_COSY: Tariff = Tariff(
    name="Octopus Cosy",
    bands=[
        TariffBand(start=time(0, 0), end=time(4, 0), rate_pence_per_kwh=27.0),
        TariffBand(start=time(4, 0), end=time(7, 0), rate_pence_per_kwh=12.0),
        TariffBand(start=time(7, 0), end=time(13, 0), rate_pence_per_kwh=27.0),
        TariffBand(start=time(13, 0), end=time(16, 0), rate_pence_per_kwh=12.0),
        TariffBand(start=time(16, 0), end=time(19, 0), rate_pence_per_kwh=42.0),
        TariffBand(start=time(19, 0), end=time(22, 0), rate_pence_per_kwh=27.0),
        # 22:00-24:00, with end-of-day represented as time(0, 0).
        TariffBand(start=time(22, 0), end=time(0, 0), rate_pence_per_kwh=12.0),
    ],
)

# Octopus Go: one cheap overnight window, standard rate the rest of the day.
#   00:00-00:30 standard, 00:30-05:30 cheap, 05:30-24:00 standard.
# Illustrative rates: cheap 8.5p, standard 27.0p per kWh.
OCTOPUS_GO: Tariff = Tariff(
    name="Octopus Go",
    bands=[
        TariffBand(start=time(0, 0), end=time(0, 30), rate_pence_per_kwh=27.0),
        TariffBand(start=time(0, 30), end=time(5, 30), rate_pence_per_kwh=8.5),
        # 05:30-24:00, with end-of-day represented as time(0, 0).
        TariffBand(start=time(5, 30), end=time(0, 0), rate_pence_per_kwh=27.0),
    ],
)

# Starter tariff for the "Custom" option in the UI: a single full-day band.
CUSTOM_DEFAULT: Tariff = Tariff(
    name="Custom",
    bands=[
        TariffBand(start=time(0, 0), end=time(0, 0), rate_pence_per_kwh=27.0),
    ],
)

PRESETS: dict[str, Tariff] = {
    OCTOPUS_COSY.name: OCTOPUS_COSY,
    OCTOPUS_GO.name: OCTOPUS_GO,
}
