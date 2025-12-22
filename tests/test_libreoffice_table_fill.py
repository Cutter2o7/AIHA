from libreoffice_table_fill import AddressEntry


def test_family_header_places_family_at_end():
    entry = AddressEntry(
        family_name="Smith",
        family_info="Family",
        address_line_1="123 Main St",
        address_apt_line="",
        address_final_line="Springfield, XY",
    )

    assert entry.formatted_text.splitlines()[0] == "Smith Family"


def test_non_family_header_keeps_prefix():
    entry = AddressEntry(
        family_name="Doe",
        family_info="John & Jane",
        address_line_1="456 Oak Ave",
        address_apt_line="Apt 7",
        address_final_line="Metropolis, ZZ",
    )

    assert entry.formatted_text.splitlines()[0] == "John & Jane Doe"
