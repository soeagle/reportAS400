"""Connessione all'AS/400 tramite ODBC (IBM i Access) oppure dati demo."""

import functools
import os

try:
    import pyodbc
except ImportError:
    pyodbc = None

try:
    import yaml
except ImportError:
    yaml = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(path=None):
    if yaml is None:
        raise SystemExit("PyYAML richiesto: pip install pyyaml")
    path = path or os.environ.get("TWG_CONFIG", os.path.join(BASE_DIR, "config.yaml"))
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class As400Connection:
    """Esegue query sulle viste di sistema QSYS2."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._conn = None

    @property
    def demo(self):
        return bool(self.cfg.get("demo_mode"))

    def connect(self):
        if self._conn is None:
            if self.demo:
                self._conn = DemoConnection()
            else:
                if pyodbc is None:
                    raise RuntimeError("pyodbc non installato: pip install pyodbc")
                a = self.cfg["as400"]
                cs = (
                    f"DRIVER={{{a['driver']}}};SYSTEM={a['system']};"
                    f"UID={a['user']};PWD={a['password']};"
                )
                self._conn = pyodbc.connect(cs)
        return self._conn

    def query(self, sql, params=()):
        return self.connect().query(sql, params)

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class DemoConnection:
    """Dati dimostrativi: replica lo stato mostrato negli screenshot
    (4 controlli in allarme su 24, ASP 64.2%, storage 90%, temp 21 GB)."""

    def query(self, sql, params=()):
        sql_l = " ".join(sql.lower().split())
        if "disk_status" in sql_l or "disk" in sql_l and "asp" not in sql_l:
            return [
                (1, "DD0001", 1, "ACTIVE", None, 0, 282.0),
                (2, "DD0002", 2, "ACTIVE", None, 0, 282.0),
                (3, "DD0003", 3, "ACTIVE", None, 0, 282.0),
                (4, "DD0004", 4, "ACTIVE", None, 0, 282.0),
                (5, "DD0005", 5, "ACTIVE", None, 0, 282.0),
                (6, "DD0006", 6, "ACTIVE", None, 0, 282.0),
                (7, "DD0007", 7, "ACTIVE", None, 0, 282.0),
            ]
        if "asp_status" in sql_l:
            return [(1, 64.2, 1663, 1058, 21)]
        if "active_job_info" in sql_l and "msgw" in sql_l:
            return [("123456/QUSER/JOB001", "MSGW", 1800, "CPF9898")]
        if "active_job_info" in sql_l and "cpu" in sql_l:
            return [(42.0,)]
        if "job_queue_info" in sql_l:
            return [("QBATCH", 3, "RELEASED"), ("QSYSNOMAX", 12, "RELEASED")]
        if "active_job_info" in sql_l and "subsystem" in sql_l:
            return [("QSYS",), ("QBATCH",), ("QINTER",), ("QCMN",)]
        if "output_queue_info" in sql_l:
            return [("QPRINT", 320, 412.5), ("QEZJOBLOG", 1500, 780.0)]
        if "sysvals" in sql_l or "system_value_info" in sql_l:
            vals = {
                "qsecurity": "30",
                "qaudctl": "*NONE",
                "qmaxsign": "3",
                "qpwdminlen": "6",
            }
            key = params[0].lower() if params else "qsecurity"
            return [(key.upper(), vals.get(key, "0"))]
        if "message_queue_info" in sql_l or "qsysopr" in sql_l:
            return [("CPF4128", "CPPEA4", "12/05/2025", "Unità disco 8 in ricostruzione")]
        if "savelib" in sql_l or "save" in sql_l:
            return [("MYLIB", 30.5)]
        raise RuntimeError(f"Query demo non prevista: {sql[:80]}")

    def close(self):
        pass


@functools.lru_cache(maxsize=1)
def get_connection():
    return As400Connection(load_config())
