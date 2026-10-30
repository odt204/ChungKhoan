import pytest

from vnsignal import cli
from vnsignal.config import load_config

CFG = load_config()


@pytest.fixture
def calls(monkeypatch):
    log = []

    def stub(name, ret=None, fail=False):
        def fn(*args):
            log.append((name, args[1:]))
            if fail:
                raise RuntimeError(f"{name} hỏng")
            return ret
        return fn

    def install(new_bars=1, fail=()):
        monkeypatch.setattr(cli, "cmd_backfill", stub("backfill", fail="backfill" in fail))
        monkeypatch.setattr(cli, "cmd_eod", stub("eod", new_bars, "eod" in fail))
        monkeypatch.setattr(cli, "cmd_fundamentals", stub("fundamentals", fail="fundamentals" in fail))
        monkeypatch.setattr(cli, "cmd_signals", stub("signals", fail="signals" in fail))
        monkeypatch.setattr(cli, "cmd_news", stub("news", fail="news" in fail))
        monkeypatch.setattr(cli, "cmd_alert", stub("alert", fail="alert" in fail))
        monkeypatch.setattr(cli, "cmd_build_site", stub("build-site", fail="build-site" in fail))
        return log

    return install


def test_run_daily_order_and_summary_on_new_bars(calls):
    log = calls(new_bars=3)
    cli.cmd_run_daily(CFG, False)
    assert [n for n, _ in log] == ["backfill", "eod", "fundamentals", "signals", "news", "alert", "build-site"]
    assert dict(log)["alert"][-1] is True       # có nến mới → gửi tổng hợp
    assert dict(log)["backfill"][-1] is False   # không ép tải lại


def test_run_daily_holiday_only_alerts_on_change(calls):
    log = calls(new_bars=0)
    cli.cmd_run_daily(CFG, False)
    assert dict(log)["alert"][-1] is False


def test_run_daily_soft_steps_do_not_stop_pipeline(calls):
    log = calls(fail=("fundamentals", "news", "alert"))
    cli.cmd_run_daily(CFG, False)
    assert [n for n, _ in log][-1] == "build-site"


def test_run_daily_stops_when_eod_fails(calls):
    log = calls(fail=("eod",))
    with pytest.raises(RuntimeError):
        cli.cmd_run_daily(CFG, False)
    assert "signals" not in [n for n, _ in log]


def test_run_daily_backfill_flag_forces(calls):
    log = calls(new_bars=0)
    cli.cmd_run_daily(CFG, True)
    assert dict(log)["backfill"][-1] is True
    assert dict(log)["alert"][-1] is True
