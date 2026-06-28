from grecis.pastpapers import extract_reading_part_a


def test_extract_reading_part_a_splits_four_texts() -> None:
    body = (
        """
Section II Reading Comprehension
Part A
Text 1
This is a policy passage. It discusses institutions and society because education matters.
"""
        + " ".join(["market regulation culture"] * 80)
        + """
21. Which of the following is true?
Text 2
This is a science passage. It examines evidence and research because climate matters.
"""
        + " ".join(["study robust significant"] * 80)
        + """
26. Which of the following is true?
Text 3
This is an economy passage. It examines firms and markets because capital matters.
"""
        + " ".join(["merger acquisition regulation"] * 80)
        + """
31. Which of the following is true?
Text 4
This is an education passage. It examines schools and discipline because learning matters.
"""
        + " ".join(["student teacher curriculum"] * 80)
        + """
36. Which of the following is true?
Part B
"""
    )
    passages = extract_reading_part_a(body)
    assert len(passages) == 4
    assert "policy passage" in passages[0]
    assert "science passage" in passages[1]
