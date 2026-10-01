from samantha_mirror.auth import MAX_FAILS, Auth


def test_valid_token():
    auth = Auth("a" * 32)
    assert auth.valid("a" * 32)
    assert not auth.valid("b" * 32)
    assert not auth.valid("")
    assert not auth.valid(None)


def test_lockout_after_repeated_failures():
    auth = Auth("a" * 32)
    for _ in range(MAX_FAILS):
        assert not auth.locked_out("1.2.3.4")
        auth.record_failure("1.2.3.4")
    assert auth.locked_out("1.2.3.4")
    assert not auth.locked_out("5.6.7.8")  # other devices are unaffected
