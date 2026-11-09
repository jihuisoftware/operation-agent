# Gateway streaming delivery contract

## Streaming delivery contract (stream-is-the-message adapters)

Adapters with `draft_stream_is_message = True` (relay Slack native streaming) keep ONE cumulative
native stream per turn; the stream IS the final message. Four invariants, each from a live
duplicate-final incident (NS-658 canary ledger, hermes#85796 / gateway-gateway#210); violating any
re-creates a duplicate or frozen stream:

1. **Draft frames are prefix-stable.** Frame N must be a string prefix of frame N+1. Never mutate
   drafts per tick — no fence-closing (`ensure_closed_code_fences`), cursor suffix, segment-state
   resets at tool boundaries, or mrkdwn conversion. A non-prefix frame forces a whole-snapshot
   re-append ("stacked copies"). The finalize path may still transform the real final.
2. **The consumer declares the final; the adapter never guesses.** `finish(final_text)` carries the
   completed `final_response` (verifier footer, completion explainer included). New post-stream
   augmentation MUST ride this payload — mutating `final_response` after the seal re-opens the
   `delivered_final_matches` mismatch → corrective duplicate send.
3. **Interim sends carry `metadata["_interim_send"] = True`.** Any consumer-side `adapter.send()`
   that is not the turn-final (commentary, segment-tail flushes) must set it or seal-interception
   seals the live stream with interim text. Seal-interception exists at BOTH egress doors (`send()`
   and `send_for_platform()`); a new egress door needs the same two checks.
4. **Reconcile by edit, never by plain send.** A lane delivering a final beside a sealed stream
   (queued follow-ups, media-accompanied finals) first tries `edit_message` on the consumer's
   `message_id`; plain `send()` only when no editable message exists. A sealed native stream is a
   regular message — `chat.update` works (live-verified).

Contract tests: `tests/gateway/test_stream_final_contract.py` (mutation-checked). Slack ground
truth: `chat.*Stream` speaks STANDARD markdown, not mrkdwn; `stopStream.markdown_text` APPENDS;
`startStream`/`stopStream` are Tier 2 (~20/min). Check `draft_stream_is_message is True` —
MagicMock adapters in older tests auto-create truthy attributes.

