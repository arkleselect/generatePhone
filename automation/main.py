"""Industrial CLI added alongside the upstream image_gen.py entry point."""
import argparse
import asyncio
import json
import logging
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from browser import launch_browser, close_browser, login_session
from config import Settings
from dataset import GenerateRequest, Journal, run_dataset
from prompts import DEFECTS


def build_parser():
    """Both underscore and hyphen flags match the documented integration contract."""
    parser = argparse.ArgumentParser(description='ChatGPT 网页账号工业缺陷数据集生成器')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('auth', help='打开浏览器登录，关闭窗口后保存会话')
    defects = sub.add_parser('defects', help='生成参考图缺陷数据集')
    defects.add_argument('--source_image', '--source-image', required=True)
    defects.add_argument('--defect_type', '--defect-type', required=True, help=' / '.join(d['datasetType'] for d in DEFECTS.values()))
    defects.add_argument('--count', type=int, default=1)
    defects.add_argument('--output_dir', '--output-dir')
    defects.add_argument('--date_text', '--date-text')
    defects.add_argument('--batch_name', '--batch-name')
    defects.add_argument('--custom_prompt_suffix', '--custom-prompt-suffix', default='')
    defects.add_argument('--headless', action=argparse.BooleanOptionalAction, default=None)
    defects.add_argument('--max_retry', '--max-retry', type=int)
    defects.add_argument('--plan-only', action='store_true', help='只生成提示词和清单，不打开浏览器')
    resume = sub.add_parser('resume', help='继续原批次；不重发提交结果不明的任务')
    resume.add_argument('directory')
    serve = sub.add_parser('serve', help='启动本机 HTTP 接口，默认不会打开浏览器')
    serve.add_argument('--port', type=int, default=8091)
    return parser


async def execute(journal, settings):
    """CLI uses the same dataset runner and browser lifecycle as HTTP/Java work."""
    pw, context, page = await launch_browser(journal.metadata['headless'], settings)
    try:
        return await run_dataset(page, journal, settings)
    finally:
        await close_browser(pw, context)


def main(argv=None):
    args_list = list(sys.argv[1:] if argv is None else argv)
    # Retain the user's requested shorthand: python main.py --source_image ...
    if args_list and args_list[0].startswith('--') and args_list[0] not in ('--help', '-h'):
        args_list.insert(0, 'defects')
    parser = build_parser(); args = parser.parse_args(args_list)
    settings = Settings.load()
    logging.basicConfig(level=settings.log_level, format='%(asctime)s %(levelname)s %(message)s')
    if args.command == 'auth':
        asyncio.run(login_session()); return 0
    if args.command == 'serve':
        import uvicorn
        from service import create_app
        # Standalone callers read a private token file; Java supplies an ephemeral process token.
        if not os.getenv('CONTROL_TOKEN'):
            settings.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            token_file = settings.state_dir / 'api-token'
            if not token_file.exists():
                token_file.write_text(secrets.token_urlsafe(32), encoding='utf-8'); token_file.chmod(0o600)
            os.environ['CONTROL_TOKEN'] = token_file.read_text(encoding='utf-8').strip()
            print('HTTP token file: ' + str(token_file), flush=True)
        uvicorn.run(create_app(settings), host='127.0.0.1', port=args.port, access_log=False)
        return 0
    try:
        if args.command == 'resume':
            journal = Journal.load(args.directory)
        else:
            request = GenerateRequest(source_image_path=args.source_image, defect_type=args.defect_type, count=args.count,
                output_dir=args.output_dir, date_text=args.date_text, batch_name=args.batch_name,
                custom_prompt_suffix=args.custom_prompt_suffix, headless=args.headless, max_retry=args.max_retry)
            journal = Journal.create(request, settings)
            if args.plan_only:
                print(json.dumps(journal.summary(), ensure_ascii=False, indent=2)); return 0
        result = asyncio.run(execute(journal, settings))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status']=='COMPLETED' and result['failed_count']==0 else 1
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        parser.error(str(exc))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
