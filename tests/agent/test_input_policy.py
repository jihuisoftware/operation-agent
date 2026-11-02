"""Parsing budgets use real config round trips and existing execution entry points."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.config import save_config
from agent.input_policy import parsing_allowed, pdf_parsing_notice


def save(**options):
    save_config({'token_saving': {'enabled': True, 'parse_images': False, 'parse_files': False, **options}}, merge_existing=True)


def test_profile_isolation_and_independent_switches(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / 'one'))
    assert parsing_allowed('images') and parsing_allowed('files')
    save(parse_files=True)
    assert not parsing_allowed('images') and parsing_allowed('files')
    assert '图像' in pdf_parsing_notice(tmp_path / 'one')
    token = set_hermes_home_override(tmp_path / 'two')
    try:
        assert parsing_allowed('images') and parsing_allowed('files')
        save(parse_images=True)
        assert parsing_allowed('images') and not parsing_allowed('files')
        assert '文件' in pdf_parsing_notice(tmp_path / 'two')
        save(enabled=False)
        assert parsing_allowed('images') and parsing_allowed('files')
    finally:
        reset_hermes_home_override(token)
    assert not parsing_allowed('images') and parsing_allowed('files')


def test_images_refused_before_pixel_read_download_or_model_call(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    save()
    from agent.image_routing import build_native_content_parts
    from tools import vision_tools
    from tui_gateway.prompt_turn import _route_turn_images
    from gateway.run_inbound import GatewayInboundMixin
    prepare = AsyncMock(side_effect=AssertionError('no pixels should be fetched'))
    monkeypatch.setattr(vision_tools, '_prepare_image', prepare)
    parts, _ = build_native_content_parts('描述图片', ['/missing.png'], ['https://example.org/image.png'])
    assert [p['type'] for p in parts] == ['text']
    assert '节省 Token' in parts[0]['text']
    assert '节省 Token' in _route_turn_images(SimpleNamespace(), '描述图片', ['/missing.png'])
    assert '节省 Token' in asyncio.run(GatewayInboundMixin._enrich_inbound_images(None, None, 's', '描述图片', ['/missing.png']))
    for result in (asyncio.run(vision_tools.vision_analyze_tool('/missing.png', '描述')), asyncio.run(vision_tools._handle_vision_analyze({'image_url': '/missing.png'}))):
        assert json.loads(result)['success'] is False
    prepare.assert_not_called()
    assert not vision_tools._native_tool_result_images('openai', 'gpt-4o', {'token_saving': {'enabled': True}})


def test_documents_and_text_references_skip_contents_without_erasing_files(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    save()
    from agent.context_references import preprocess_context_references
    from tools.file_tools import read_file_tool
    text = tmp_path / 'attachment.txt'
    text.write_text('UNIQUE_ATTACHMENT_CONTENT')
    document = tmp_path / 'report.docx'
    document.write_bytes(b'not a valid document, parsing must not start')
    result = preprocess_context_references('读取 @file:attachment.txt', cwd=tmp_path, context_length=100_000)
    assert 'UNIQUE_ATTACHMENT_CONTENT' not in result.message
    assert '节省 Token' in result.message
    assert '节省 Token' in read_file_tool(str(document), task_id='token-saving')
    assert text.read_text() == 'UNIQUE_ATTACHMENT_CONTENT'
    save(parse_files=True)
    result = preprocess_context_references('读取 @file:attachment.txt', cwd=tmp_path, context_length=100_000)
    assert 'UNIQUE_ATTACHMENT_CONTENT' in result.message
