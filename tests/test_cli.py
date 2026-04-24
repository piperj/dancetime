import pytest
from dancetime_cli import build_parser


def test_all_subcommands_exist():
    parser = build_parser()
    subparsers = next(
        a for a in parser._actions if hasattr(a, "_name_parser_map")
    )
    assert set(subparsers._name_parser_map.keys()) >= {"scrape", "heats", "ranking", "publish", "schedule"}


def test_scrape_requires_cyi():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["scrape"])


def test_heats_requires_cyi():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["heats"])


def test_ranking_cyi_optional():
    parser = build_parser()
    args = parser.parse_args(["ranking"])
    assert args.cyi is None


def test_scrape_force_flag():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--cyi", "373", "--force"])
    assert args.force is True
    args2 = parser.parse_args(["scrape", "--cyi", "373"])
    assert args2.force is False


def test_ranking_iterations():
    parser = build_parser()
    args = parser.parse_args(["ranking", "--cyi", "373", "--iterations", "50"])
    assert args.iterations == 50
    args2 = parser.parse_args(["ranking", "--cyi", "373"])
    assert args2.iterations == 100


def test_publish_deploy_flag():
    parser = build_parser()
    args = parser.parse_args(["publish", "--deploy"])
    assert args.deploy is True
    args2 = parser.parse_args(["publish"])
    assert args2.deploy is False


def test_default_dirs():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--cyi", "373"])
    assert args.data_dir == "data/raw"

    args = parser.parse_args(["heats", "--cyi", "373"])
    assert args.data_dir == "data/raw"
    assert args.out_dir == "data"

    args = parser.parse_args(["ranking", "--cyi", "373"])
    assert args.out_dir == "data"
