"""内置调度器（四职责）：班次（08:00/21:00）+ 到期提醒 + 主动扫描（每 3h）+ 周记忆固化（周日 22 点）。

从 daemon.py 独立（2026-10-14，ADR-004）：daemon 通过 start(tg_client, daemon, stop) 挂载；
本模块只依赖 daemon 对象暴露的 run_shift / run_reflect / _say / log 鸭子接口与 daemon_state。
班次 prompt 外置于 prompts/shift-<kind>.md（由 daemon.run_shift 读取）。
"""

import threading
import time
from datetime import datetime

from daemon_state import load_state, save_state


def _should_fire_shift(now, kind, done_dates):
    """班次触发判定：morning 在 08:00-08:59 / evening 在 21:00-21:59，当天未跑过即触发。"""
    hour = 8 if kind == "morning" else 21
    return now.hour == hour and now.strftime("%Y-%m-%d") != done_dates.get(kind)


def _check_reminders(daemon):
    """到期提醒即发即销（reminders 存 state.json，remind_in 工具写入）。"""
    rems = load_state().get("reminders") or []
    if not rems:
        return
    now = time.time()
    due = [r for r in rems if r["due"] <= now]
    if not due:
        return
    for r in due:
        daemon._say(f"⏰ 提醒：{r['text']}")
    save_state(reminders=[r for r in rems if r["due"] > now])


def _proactive_scan(daemon):
    """主动扫描：Trending 出现高热（日增≥3000）新面孔才推送，同项不重复（state 去重）。"""
    import importlib.util
    import re as _re
    from datetime import date as _date
    now = datetime.now()
    if not (9 <= now.hour < 22):
        return
    st = load_state()
    if st.get("proactive_date") != now.strftime("%Y-%m-%d"):
        st["proactive_date"] = now.strftime("%Y-%m-%d")
        save_state(**st)
    try:
        import sys
        from pathlib import Path
        src = Path(__file__).resolve().parent.parent / "integrations" / "sources" / "github_trending.py"
        if str(src.parent) not in sys.path:  # 插件依赖同目录 _common（与 tools.trending_top 同款处理）
            sys.path.insert(0, str(src.parent))
        spec = importlib.util.spec_from_file_location("ps_trending", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        data, _ = mod.fetch(_date.today(), since="today")
    except Exception as e:  # noqa: BLE001 —— 扫描是增值不是承诺，失败静默
        daemon.log.log("err", err=f"proactive: {e}")
        return
    seen = set(load_state().get("proactive_seen") or [])
    fresh = [r for r in (data or [])[:5]
             if r["name"] not in seen and r.get("stars_today", 0) >= 3000]
    if fresh:
        body = "\n".join(f"· {r['name']} — +{r['stars_today']:,}/日，{r['desc'][:40]}"
                         for r in fresh)
        daemon._say(f"🔥 Trending 速报：出现高热新面孔\n{body}\n（主动扫描，如需深读说一声）")
    save_state(proactive_seen=sorted(seen | {r["name"] for r in fresh})[-100:])


def _weekly_reflect(daemon):
    """周日 22 点记忆固化（跑 daemon.run_reflect，LLM 归并日志→observations）。"""
    now = datetime.now()
    week = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    if load_state().get("reflect_week") == week:
        return
    save_state(reflect_week=week)
    daemon.run_reflect()


def _scheduler_loop(tg_client, daemon, stop):
    last_scan = 0
    while not stop["flag"]:
        try:
            now = datetime.now()
            done = load_state().get("shifts", {})
            for kind in ("morning", "evening"):
                if _should_fire_shift(now, kind, done):
                    shifts = load_state().get("shifts", {})
                    shifts[kind] = now.strftime("%Y-%m-%d")  # 先记账防重入
                    save_state(shifts=shifts)
                    daemon.log.log("shift", kind=kind, note="调度器触发")
                    threading.Thread(target=daemon.run_shift, args=(kind,), daemon=True).start()
            _check_reminders(daemon)
            if time.time() - last_scan >= 3 * 3600:
                last_scan = time.time()
                threading.Thread(target=_proactive_scan, args=(daemon,), daemon=True).start()
            if 22 <= now.hour < 23:
                _weekly_reflect(daemon)
        except Exception as e:  # noqa: BLE001 —— 调度器自身绝不死
            try:
                daemon.log.log("err", err=f"scheduler: {type(e).__name__}: {e}")
            except Exception:  # noqa: BLE001
                pass
        stop["flag"] or time.sleep(30)


def start(tg_client, daemon, stop):
    """挂载调度器线程（daemon.run 调用）。"""
    threading.Thread(target=_scheduler_loop, args=(tg_client, daemon, stop), daemon=True).start()
