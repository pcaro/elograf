from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional

from eloGraf.settings import Settings
from eloGraf.stt_factory import get_available_engines, describe_engine
from eloGraf.engine_plugin import get_plugin


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Place an icon in systray to launch offline speech recognition."
    )
    parser.add_argument("-l", "--log", help="specify the log level", dest="loglevel")
    parser.add_argument("--version", help="show version and exit", action="store_true")
    parser.add_argument("-s", "--begin", help="begin dictation (or launch if not running)", action="store_true")
    parser.add_argument("--end", help="end dictation in running instance", action="store_true")
    parser.add_argument("--exit", help="exit the running instance", action="store_true")
    parser.add_argument("--list-models", help="list available models", action="store_true")
    parser.add_argument("--set-model", help="set the active model by name", metavar="MODEL_NAME")
    parser.add_argument("--list-engines", help="list available STT engines", action="store_true")
    parser.add_argument("--use-engine", help="use STT engine for this session only", metavar="ENGINE_NAME")
    parser.add_argument("--resume", help="resume dictation if suspended", action="store_true")
    parser.add_argument("--suspend", help="suspend dictation in running instance", action="store_true")
    parser.add_argument("--toggle", help="toggle dictation (start/suspend/resume)", action="store_true")
    return parser


@dataclass
class CliExit:
    code: int
    stdout: str = ""
    stderr: str = ""


AVAILABLE_ENGINES = get_available_engines()


def validate_engine(engine_name: str) -> Optional[CliExit]:
    """Validate engine name and return error if invalid."""
    try:
        get_plugin(engine_name)
        return None
    except ValueError:
        available = "\n".join(
            f"  - {name} ({describe_engine(name)})" for name in AVAILABLE_ENGINES
        )
        message = (
            f"✗ Engine '{engine_name}' not found\n\n"
            f"Available engines:\n{available}\n"
        )
        return CliExit(code=1, stderr=message)



def handle_engine_commands(args, settings: Settings) -> Optional[CliExit]:
    """Handle CLI options related to STT engine selection and listing."""
    list_engines = getattr(args, "list_engines", False)
    engine_override = getattr(args, "use_engine", None)

    if not list_engines and not engine_override:
        return None

    settings.load()

    if list_engines:
        current_engine = settings.sttEngine
        lines = ["Available STT engines:", "-" * 80]
        for engine in AVAILABLE_ENGINES:
            marker = "●" if engine == current_engine else " "
            display = describe_engine(engine)
            lines.append(f"{marker} {engine} — {display}")
        lines.append("")
        return CliExit(code=0, stdout="\n".join(lines) + "\n")

    if engine_override:
        # Validate but don't exit - let the app start with this engine
        error = validate_engine(engine_override)
        if error:
            return error

    return None


def handle_model_commands(args, settings: Settings) -> Optional[CliExit]:
    """Handle CLI options related to model management."""
    # Check engine commands first
    engine_result = handle_engine_commands(args, settings)
    if engine_result is not None:
        return engine_result

    list_models = getattr(args, "list_models", False)
    model_to_set = getattr(args, "set_model", None)

    if not list_models and not model_to_set:
        return None

    settings.load()

    if list_models:
        if not settings.models:
            return CliExit(
                code=0,
                stdout=(
                    "No models configured\n\n"
                    "Use the GUI (elograf) to download or import models\n"
                ),
            )

        current_model = settings.value("Model/name") if settings.contains("Model/name") else ""
        lines = ["Available models:", "-" * 80]
        for model in settings.models:
            marker = "●" if model["name"] == current_model else " "
            lines.extend(
                [
                    f"{marker} {model['name']}",
                    f"  Language: {model['language']}",
                    f"  Type: {model['type']}",
                    f"  Version: {model['version']}",
                    f"  Size: {model['size']}",
                    f"  Location: {model['location']}",
                    "",
                ]
            )
        return CliExit(code=0, stdout="\n".join(lines) + "\n")

    if model_to_set:
        model_name = model_to_set
        for model in settings.models:
            if model["name"] == model_name:
                settings.setValue("Model/name", model_name)
                return CliExit(code=0, stdout=f"✓ Model set to '{model_name}'\n")
        available = "\n".join(f"  - {model['name']}" for model in settings.models)
        message = (
            f"✗ Model '{model_name}' not found\n\n"
            f"Available models:\n{available}\n"
        )
        return CliExit(code=1, stderr=message)

    return None


def choose_ipc_command(args) -> Optional[str]:
    if args.exit:
        return "exit"
    if args.end:
        return "end"
    if args.begin:
        return "begin"
    if getattr(args, "resume", False):
        return "resume"
    if getattr(args, "suspend", False):
        return "suspend"
    if getattr(args, "toggle", False):
        return "toggle"
    return None
