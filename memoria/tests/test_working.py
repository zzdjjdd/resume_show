from memoria.stores.working import WorkingMemory, approx_token_count


def test_append_and_order() -> None:
    wm = WorkingMemory()
    wm.append("user", "hi")
    wm.append("assistant", "hello")
    assert [m.content for m in wm.messages] == ["hi", "hello"]
    assert len(wm) == 2


def test_max_messages_window() -> None:
    wm = WorkingMemory(max_messages=2)
    for i in range(5):
        wm.append("user", f"m{i}")
    assert [m.content for m in wm.messages] == ["m3", "m4"]


def test_max_tokens_window() -> None:
    wm = WorkingMemory(max_tokens=10, token_counter=len)
    wm.append("user", "aaaaa")  # 5
    wm.append("user", "bbbbb")  # 10
    wm.append("user", "ccccc")  # 15 -> drop oldest -> 10
    assert [m.content for m in wm.messages] == ["bbbbb", "ccccc"]


def test_keeps_at_least_one_message() -> None:
    wm = WorkingMemory(max_tokens=1, token_counter=len)
    wm.append("user", "a very long message")
    assert len(wm) == 1


def test_token_count_with_custom_counter() -> None:
    wm = WorkingMemory(token_counter=lambda _text: 1)
    wm.append("user", "x")
    wm.append("user", "y")
    assert wm.token_count() == 2


def test_render_and_clear() -> None:
    wm = WorkingMemory()
    wm.append("user", "hi")
    wm.append("assistant", "yo")
    assert wm.render() == "user: hi\nassistant: yo"
    wm.clear()
    assert len(wm) == 0


def test_approx_token_count() -> None:
    assert approx_token_count("") == 1
    assert approx_token_count("a" * 8) == 2
