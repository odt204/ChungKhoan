from vnsignal.data.base import MarketDataSource


def get_source(name: str) -> MarketDataSource:
    if name.upper() == "VCI":
        from vnsignal.data.vci import VCISource

        return VCISource()
    raise ValueError(f"Nguồn dữ liệu không hỗ trợ: {name}")
