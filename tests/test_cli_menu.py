from marketmood import cli


def test_menu_language():
    assert cli.menu_lang({"LANG": "zh_CN.UTF-8"}) == "zh"
    assert cli.menu_lang({"LANG": "en_US.UTF-8"}) == "en"
    assert cli.menu_lang({"MARKETMOOD_LANG": "zh", "LANG": "en_US"}) == "zh"


def test_menu_commands_exist_and_groups_shown():
    choices = cli.build_parser()._subparsers._group_actions[0].choices
    for lang in ("zh", "en"):
        for _, rows in cli.MENU[lang]:
            for cmd, _ in rows:
                assert cmd.split()[0] in choices
    text = cli.menu_text("zh")
    for g in ("日常看盘", "选股与评分卡", "研究与量化实验室", "持仓体检"):
        assert g in text


def test_no_args_prints_menu(capsys, monkeypatch):
    monkeypatch.setenv("MARKETMOOD_LANG", "en")
    try:
        cli.main([])
    except SystemExit as e:
        assert e.code == 0
    assert "Portfolio check-up" in capsys.readouterr().out
