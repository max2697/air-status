from air_status.providers.gogo import GogoProvider


class AirCanada(GogoProvider):
    """Air Canada Wi-Fi runs on the Gogo / Intelsat portal."""

    id = "aircanada"
    name = "Air Canada"
    airline_code = "ACA"
