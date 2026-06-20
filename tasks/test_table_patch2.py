"""验证 Table._new 补丁（extend_existing=True）"""
from sqlalchemy import Table, Column, Integer, MetaData

# 手动补丁
_orig = Table._new

def _patched(cls, *args, **kw):
    kw["extend_existing"] = True
    return _orig(*args, **kw)

Table._new = classmethod(_patched)

m = MetaData()
t = Table("test_table", m, Column("id", Integer, primary_key=True))
print(f"1st create OK: {t.name}")

try:
    t2 = Table("test_table", m, Column("id", Integer, primary_key=True))
    print(f"2nd create OK: extend_existing=True works!")
except Exception as e:
    print(f"2nd create FAILED: {e}")
