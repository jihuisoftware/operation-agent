"""The forensic reader preserves recorded usage fields."""


def test_forensics_parser_reads_the_new_fields(tmp_path):
    from evals.postmortem.forensics.logcalls import parse_logs
    log = tmp_path / "agent.log"
    log.write_text(
        "2026-09-06 19:32:08,549 INFO [s1] agent.conversation_loop: API call #3: model=anthropic/claude-fable-5.1 provider=nous "
        "in=62889 out=7 total=62896 latency=0.2s cache=34283/62889 (55%) write=28604 id=gen-1788636728-qMa1 upstream=Claude Platform on AWS\n"
        "2026-09-06 19:32:09,549 INFO [s1] agent.conversation_loop: API call #4: model=anthropic/claude-fable-5.1 provider=nous "
        "in=91079 out=7 total=91086 latency=0.2s cache=62887/91079 (69%)\n", encoding="utf-8")
    calls = parse_logs([str(log)], {"s1"})
    assert [c["n"] for c in calls] == [3, 4]
    assert calls[0]["write"] == 28604 and calls[0]["id"] == "gen-1788636728-qMa1" and calls[0]["upstream"] == "Claude Platform on AWS"
    assert "write" not in calls[1] and "id" not in calls[1]

