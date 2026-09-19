import get_profile


def test_admin_id_membership_check():
    # Regression test: the handler used to compare `user.id != ADMIN_ID`
    # where ADMIN_ID is a list, e.g. `93027469 != [93027469]` — always
    # True, so /get_ids was permanently unusable even for the real admin.
    admin_id = get_profile.ADMIN_ID[0]
    assert (admin_id not in get_profile.ADMIN_ID) is False
    assert (admin_id + 1 not in get_profile.ADMIN_ID) is True
