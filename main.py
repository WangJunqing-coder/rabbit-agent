#!/usr/bin/env python3
"""
Rabbit Agent - local AI coding assistant

Usage:
    python main.py                    # CLI mode
    python main.py --tui              # TUI mode (prompt_toolkit)
    python main.py -c "your question" # Single query
    python main.py --config config.yaml
"""
import asyncio
import argparse
import sys
import os

from config import Config, PROVIDER_PRESETS


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rabbit Agent - Local AI Coding Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-c", "--command", help="Single query mode", type=str)
    parser.add_argument("--tui", action="store_true", help="Use TUI mode (prompt_toolkit)")
    parser.add_argument("--config", help="Config file path", type=str)
    parser.add_argument("--provider", help="LLM provider", type=str)
    parser.add_argument("--model", help="Model name", type=str)
    parser.add_argument("--api-base", help="API base URL", type=str)
    parser.add_argument("--api-key", help="API key", type=str)
    return parser.parse_args()


def apply_args_to_config(args, config):
    if args.provider:
        config.llm.provider = args.provider
        if args.provider in PROVIDER_PRESETS:
            preset = PROVIDER_PRESETS[args.provider]
            config.llm.api_base = preset["api_base"]
            if not args.model:
                config.llm.model = preset["models"][0]
    if args.model:
        config.llm.model = args.model
    if args.api_base:
        config.llm.api_base = args.api_base
    if args.api_key:
        config.llm.api_key = args.api_key
    return config


def main():
    args = parse_args()
    config = Config.load(args.config)
    config = apply_args_to_config(args, config)

    try:
        if args.tui:
            from tui import run_tui_mode
            asyncio.run(run_tui_mode(config, args.command))
        else:
            from cli import run_cli_mode
            asyncio.run(run_cli_mode(config, args.command))
    except KeyboardInterrupt:
        print("\nInterrupted")


if __name__ == "__main__":
    main()
