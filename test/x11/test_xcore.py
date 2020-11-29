from libqtile.backend.x11 import xcore


def test_keys(qtile_nospawn):
    assert "a" in xcore.get_keys()
    assert "shift" in xcore.get_modifiers()


def test_no_two_qtiles(qtile):
    try:
        xcore.XCore(qtile.display)
    except xcore.ExistingWMException:
        pass
    else:
        raise Exception("excpected an error on multiple qtiles connecting")
