"""测试 Table.__init__ 补丁是否生效"""
from sqlalchemy import Table, Column, Integer, MetaData

# 手动补丁
_orig = Table.__init__
called = False

def _patched(self, *args, **kwargs):
    global called
    called = True
    kwargs.setdefault("extend_existing", True)
    return _orig(self, *args, **kwargs)

Table.__init__ = _patched

# 创建 Table
m = MetaData()
t = Table("test_table", m, Column("id", Integer, primary_key=True))
print(f"补丁被调用: {called}")
print(f"t.extend_existing: {getattr(t, 'extend_existing', 'NOT_SET')}")

# 测试重复创建 - 如果不报错说明 extend_existing 生效
try:
    t2 = Table("test_table", m, Column("id", Integer, primary_key=True))
    print(f"第二次创建成功! extend_existing 生效")
    print(f"t2.extend_existing: {getattr(t2, 'extend_existing', 'NOT_SET')}")
except Exception as e:
    print(f"第二次创建失败: {e}")
