"""Supervisor readback contracts, not actual namespace qualification."""
import pytest
from tools.namespace_diagnostics import cleanup_verified


@pytest.mark.parametrize('stop,final,state,expected',[
    (0,0,'ActiveState=inactive\nControlGroup=\nLoadState=loaded\n',True),
    (5,0,'ActiveState=inactive\nControlGroup=\nLoadState=not-found\n',True),
    (5,0,'ActiveState=inactive\nControlGroup=\nLoadState=loaded\n',False),
    (0,1,'ActiveState=inactive\nControlGroup=\nLoadState=not-found\n',False),
    (0,0,'ActiveState=active\nControlGroup=\nLoadState=loaded\n',False),
    (0,0,'ActiveState=failed\nControlGroup=/system.slice/fixed.service\n',False),
    (0,0,'ActiveState=inactive\n',False),
])
def test_cleanup_requires_inactive_unit_and_absent_control_group(stop,final,state,expected):
    assert cleanup_verified(stop,final,state) is expected
