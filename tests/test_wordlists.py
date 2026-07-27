from grecis.wordlists import (
    common_american_20k,
    gaokao_words,
    gre_words,
    kaoyan_words,
    match_vocabulary_tier,
    tier_importance,
    vocabulary_tier,
)


def test_local_word_lists_load_expected_scale() -> None:
    assert len(gaokao_words()) >= 3500
    assert len(kaoyan_words()) >= 5500
    assert len(common_american_20k()) == 20_000
    assert len(gre_words()) >= 2900


def test_vocabulary_tiers_are_disjoint_and_have_stable_importance() -> None:
    core = next(word for word in kaoyan_words() if vocabulary_tier(word) == "core")
    key = next(word for word in common_american_20k() if vocabulary_tier(word) == "key")

    assert vocabulary_tier(core) == "core"
    assert vocabulary_tier(key) == "key"
    gre = next(word for word in gre_words() if vocabulary_tier(word) == "gre")

    assert vocabulary_tier(gre) == "gre"
    assert vocabulary_tier("paleobiogeographically") == "rare"
    assert tier_importance("core") == 5
    assert tier_importance("key") == 4
    assert tier_importance("gre") == 3
    assert tier_importance("rare") == 1


def test_inflected_forms_match_their_word_list_entry() -> None:
    gre = next(
        word
        for word in gre_words()
        if word.endswith("e")
        and f"{word[:-1]}ing" not in gre_words()
        and word not in common_american_20k()
        and word not in kaoyan_words()
        and word not in gaokao_words()
    )

    assert match_vocabulary_tier(f"{gre[:-1]}ing") == (gre, "gre")
    assert match_vocabulary_tier("is") == ("be", "high_school")
    assert match_vocabulary_tier("wars") == ("war", "high_school")
    assert match_vocabulary_tier("players") == ("player", "high_school")
    assert match_vocabulary_tier("rules") == ("rule", "high_school")
    assert match_vocabulary_tier("you’re") == ("you", "high_school")
    assert match_vocabulary_tier("re") == ("be", "high_school")
