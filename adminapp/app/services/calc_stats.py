from datetime import datetime, timedelta

from app.core.db_controller import ApplianceDB

def calc_stats(stats):
    today = datetime.now().date()
    start_ts = int(datetime.combine(today, datetime.min.time()).timestamp())
    end_ts = int((datetime.combine(today, datetime.min.time()) + timedelta(days=1)).timestamp())

    todayPlans = [t for t in stats if t.get("plan_time", 0) >= start_ts and t.get("plan_time", 0) < end_ts]
    todaySends = [t for t in stats if t.get("send_time", 0) >= start_ts and t.get("send_time", 0) < end_ts and t.get("send_time", 0) != 0]
    todaySuccess = [t for t in todaySends if str(t.get("send_res", "")).startswith("True")]
    totalSends = [t for t in stats if t.get("send_time", 0) != 0]

    return {
        "totalplanned": len(stats),
        "todayplanned": len(todayPlans),
        "todaysent": len(todaySends),
        "todaysuccess": len(todaySuccess),
        "totalsent": len(totalSends),
        "stats_date": today
    }


async def update_sendlog_stats(db: ApplianceDB):
    """Update the sendlog_stats table with statistics for each sendtask."""
    sendtasks = await db.get_db("sendtasks", column_names=["sendtask_uuid"])
    for task in sendtasks:
        uuid = task["sendtask_uuid"]
        sendlog = await db.get_db(uuid)
        stats = calc_stats(sendlog)
        await db.upsert_db("sendlog_stats", {
            "sendtask_uuid": uuid,
            **stats
        }, conflict_keys=["sendtask_uuid"])