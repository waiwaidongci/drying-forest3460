from ..services import monitor
class MonitorController:
    list=staticmethod(monitor.list_plans)
    create=staticmethod(monitor.create_plan)
    detail=staticmethod(monitor.plan_detail)
    reading=staticmethod(monitor.submit_reading)
    correct=staticmethod(monitor.submit_correction)
    corrections=staticmethod(monitor.list_corrections)
