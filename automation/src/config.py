"""Local worker configuration; no API key or account password is required."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)


def boolean(value: str) -> bool:
    """Reject misspelled settings rather than silently changing execution mode."""
    if value.lower() not in {'true', 'false', '1', '0'}:
        raise ValueError('Boolean configuration must be true or false')
    return value.lower() in {'true', '1'}


@dataclass(frozen=True)
class Settings:
    profile_dir: Path
    output_dir: Path
    input_root: Path
    state_dir: Path
    headless: bool
    max_retry: int
    timeout: int
    log_level: str
    channel: str

    @classmethod
    def load(cls):
        """Environment overrides automation/.env; Java supplies the shared state directory."""
        state = Path(os.getenv('BROWSER_STATE_DIR', ROOT.parent / 'data/browser')).resolve()
        settings = cls(
            Path(os.getenv('BROWSER_PROFILE_DIR', state / 'profile')).resolve(),
            Path(os.getenv('DATASET_ROOT', ROOT.parent / 'dataset')).resolve(),
            Path(os.getenv('INPUT_ROOT', ROOT.parent / 'data')).resolve(), state,
            boolean(os.getenv('HEADLESS', 'false')), int(os.getenv('MAX_RETRY', '2')),
            int(os.getenv('GENERATION_TIMEOUT', '900')), os.getenv('LOG_LEVEL', 'INFO').upper(),
            os.getenv('BROWSER_CHANNEL', 'chrome'))
        if not 0 <= settings.max_retry <= 10 or not 10 <= settings.timeout <= 3600:
            raise ValueError('MAX_RETRY must be 0..10; GENERATION_TIMEOUT must be 10..3600')
        if settings.log_level not in {'DEBUG', 'INFO', 'WARNING', 'ERROR'}:
            raise ValueError('Invalid LOG_LEVEL')
        return settings
