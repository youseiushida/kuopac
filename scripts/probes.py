"""
Probe definitions. Each function takes a Probe instance and runs one logical
investigation. Register new ones in REGISTRY at the bottom.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from typing import Callable

from probe import Probe


# -- 01: warm-up & form schema ------------------------------------------------

def p01_landing(p: Probe) -> None:
    """Fetch the search landing page and extract CSRF + opkey baseline."""
    p.get("/opac/opac_search/", params={"lang": "0"}, label="01_landing")


# -- 02: simple searches -------------------------------------------------------

def p02_simple_search_hit(p: Probe) -> None:
    """Simple search with a keyword that hits many records."""
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
            "kywd": "機械学習", "index_amazon_s": "Books", "node_s": "",
        },
        label="02a_simple_kikai",
    )


def p02b_simple_search_zero(p: Probe) -> None:
    """Simple search with gibberish to see the zero-hit page."""
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
            "kywd": "zzz_no_such_keyword_xyz9999",
        },
        label="02b_simple_zero",
    )


def p02c_simple_search_isbn(p: Probe) -> None:
    """Simple search with a raw ISBN."""
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
            "kywd": "9784297153496",
        },
        label="02c_simple_isbn",
    )


# -- 03: advanced search -------------------------------------------------------

def p03a_adv_title(p: Probe) -> None:
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "1",
            "kywd": "",
            "kywd1_exp": "深層学習", "con1_exp": "titlekey_ja",
            "kywd2_exp": "", "con2_exp": "alkey", "op2_exp": "AND",
            "kywd3_exp": "", "con3_exp": "pubkey", "op3_exp": "AND",
            "file_exp": ["1", "3"],
            "dpmc_exp": "all",
            "sort_exp": "6", "disp_exp": "20",
        },
        label="03a_adv_title",
    )


def p03b_adv_pagination(p: Probe) -> None:
    """Try pagination on a many-hit query (start=21)."""
    # First fetch page 1 (and capture opkey)
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "1",
            "kywd1_exp": "Python", "con1_exp": "titlekey_ja",
            "file_exp": ["1"], "dpmc_exp": "all",
            "sort_exp": "6", "disp_exp": "20",
        },
        label="03b1_adv_python_page1",
    )
    # Page 2 via amode=22 with start=21
    if p.last_opkey:
        p.get(
            "/opac/opac_search/",
            params={
                "lang": "0", "amode": "22", "opkey": p.last_opkey,
                "start": "21", "cmode": "0", "place": "",
                "list_disp": "20", "list_sort": "6",
            },
            label="03b2_adv_python_page2",
        )


def p03c_adv_year_range(p: Probe) -> None:
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "1",
            "kywd1_exp": "Python", "con1_exp": "titlekey_ja",
            "year1_exp": "2020", "year2_exp": "2023",
            "file_exp": ["1"], "dpmc_exp": "all",
            "sort_exp": "5", "disp_exp": "20",
        },
        label="03c_adv_year_range",
    )


def p03d_adv_isbn_field(p: Probe) -> None:
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "1",
            "kywd1_exp": "9784297153496", "con1_exp": "isbn",
            "file_exp": ["1"], "dpmc_exp": "all",
            "sort_exp": "6", "disp_exp": "20",
        },
        label="03d_adv_isbn",
    )


def p03e_adv_three_conditions(p: Probe) -> None:
    """All three conditions filled, mixed operators."""
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "1",
            "kywd1_exp": "機械学習", "con1_exp": "titlekey_ja",
            "op2_exp": "AND", "kywd2_exp": "Python", "con2_exp": "all",
            "op3_exp": "NOT", "kywd3_exp": "入門", "con3_exp": "titlekey_ja",
            "file_exp": ["1"], "dpmc_exp": "all",
            "sort_exp": "6", "disp_exp": "20",
        },
        label="03e_adv_three_cond",
    )


# -- 04: CiNii (cmode=5) -------------------------------------------------------

def p04_cinii_simple(p: Probe) -> None:
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "5", "smode": "0",
            "kywd": "機械学習", "index_amazon_s": "Books", "node_s": "",
        },
        label="04a_cinii_simple",
    )


def p04b_cinii_adv(p: Probe) -> None:
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "5", "smode": "1",
            "titlekey_ja_ciniibooks": "深層学習",
            "ciniibooks_file_exp": "1",
            "sort_ciniibooks": "3", "ciniibooks_disp": "20",
        },
        label="04b_cinii_adv",
    )


# -- 05: details ---------------------------------------------------------------

def p05a_detail_book(p: Probe) -> None:
    """Detail page of the bibid known to exist (from HAR)."""
    p.get(
        "/opac/opac_details/",
        params={
            "lang": "0", "amode": "11", "bibid": "BB08818020",
        },
        label="05a_detail_BB08818020",
    )


def p05b_detail_ebook(p: Probe) -> None:
    """Detail page of an ebook."""
    p.get(
        "/opac/opac_details/",
        params={
            "lang": "0", "amode": "11", "bibid": "EB13920383",
        },
        label="05b_detail_EB13920383_ebook",
    )


def p05c_detail_via_permalink(p: Probe) -> None:
    p.get("/opac/opac_link/bibid/BB08818020", label="05c_permalink")


def p05d_cinii_detail(p: Probe) -> None:
    p.get(
        "/opac/opac_detail_ciniibooks/",
        params={
            "lang": "0", "ncid": "BD18537825",
        },
        label="05d_cinii_detail",
    )


# -- 06: AJAX endpoints --------------------------------------------------------

def p06a_suggest(p: Probe) -> None:
    for q in ["機械", "Python", "高速デジタル"]:
        p.get(
            "/opac/opac_suggest/",
            params={"q_word": q},
            label=f"06a_suggest_{q}",
            extra_headers={"X-Requested-With": "XMLHttpRequest"},
        )


def p06b_spellcheck(p: Probe) -> None:
    # need a prior search to get opkey
    if not p.last_opkey:
        p.get("/opac/opac_search/", params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
            "kywd": "Python",
        }, label="06b_pre_search_for_spell")
    if p.last_opkey:
        p.get(
            "/opac/opac_spellcheck/",
            params={"lang": "0", "opkey": p.last_opkey, "srvce": "0", "tikey": ""},
            label="06b_spellcheck",
            extra_headers={"X-Requested-With": "XMLHttpRequest"},
        )


def p06c_facets(p: Probe) -> None:
    if not p.last_opkey:
        p.get("/opac/opac_search/", params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
            "kywd": "機械学習",
        }, label="06c_pre_search_for_facets")
    for ft in ["datatype", "yearkey", "fpub", "txtl", "fsh", "fcls", "fauth", "dptidpl", "uclibcd"]:
        if not p.last_opkey:
            break
        p.get(
            "/opac/opac_facet/",
            params={
                "lang": "0", "opkey": p.last_opkey, "facet_type": ft,
                "amode": "2", "cmode": "0", "place": "",
                "list_disp": "20", "list_sort": "6",
            },
            label=f"06c_facet_{ft}",
            extra_headers={"X-Requested-With": "XMLHttpRequest"},
        )


def p06d_localhold(p: Probe) -> None:
    """POST opac_search_localhold with known bibids."""
    if not p.last_csrf or not p.last_opkey:
        p.get("/opac/opac_search/", params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
            "kywd": "機械学習",
        }, label="06d_pre_search_for_localhold")
    rec = json.dumps([
        {"bibid": "BB08818020", "datatype": "10", "fieldcd": "", "mtid": ""},
        {"bibid": "EB13920383", "datatype": "19", "fieldcd": "ONLINE", "mtid": "ssj0000074569"},
    ], ensure_ascii=False)
    q_param = f"opkey={p.last_opkey or ''}&start=&totalnum=2&list_disp=20&list_sort=6"
    p.post(
        "/opac/opac_search_localhold/",
        data={
            "csrfmiddlewaretoken": p.last_csrf or "",
            "lang": "0", "place": "", "mdptid": "",
            "q_param": q_param,
            "rec": rec,
        },
        label="06d_localhold",
        extra_headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": p.last_csrf or "",
        },
    )


def p06e_imgoutlink(p: Probe) -> None:
    if not p.last_csrf:
        p.get("/opac/opac_search/", params={"lang": "0"}, label="06e_pre_for_img")
    isbn_list = json.dumps([
        {"bibid": "BB08818020", "isbn": "9784297153496", "jfcd": "2",
         "datatype": "10", "thfmt": "", "ncid": "BD14456776", "nbn": "JP24215802"},
    ], ensure_ascii=False)
    p.post(
        "/opac/opac_imgoutlink/",
        data={
            "csrfmiddlewaretoken": p.last_csrf or "",
            "size": "1", "isbn_list": isbn_list,
            "img_param": "bookplus,openbd",
        },
        label="06e_imgoutlink_post",
        extra_headers={"X-Requested-With": "XMLHttpRequest",
                       "X-CSRFToken": p.last_csrf or ""},
    )
    # GET form (single-shot)
    p.get(
        "/opac/opac_imgoutlink/",
        params={
            "isbn": "9784297153496", "ncid": "BD14456776", "nbn": "JP24215802",
            "jfcd": "1", "datatype": "10", "img_param": "bookplus,openbd",
            "size": "1", "lang": "0", "bibid": "BB08818020",
        },
        label="06e_imgoutlink_get",
        extra_headers={"X-Requested-With": "XMLHttpRequest"},
    )


def p06f_stamp(p: Probe) -> None:
    if not p.last_csrf:
        p.get("/opac/opac_search/", params={"lang": "0"}, label="06f_pre_for_stamp")
    bibid_list = json.dumps([
        {"bibid": "BB08818020", "kind": "BBBOOK",
         "isbn": "9784297153496", "issn": ""},
    ], ensure_ascii=False)
    p.post(
        "/opac/opac_stamp/",
        data={
            "csrfmiddlewaretoken": p.last_csrf or "",
            "bibid_list": bibid_list, "lang": "0",
        },
        label="06f_stamp_post",
        extra_headers={"X-Requested-With": "XMLHttpRequest",
                       "X-CSRFToken": p.last_csrf or ""},
    )


def p06g_openbd_bookplus(p: Probe) -> None:
    p.get(
        "/opac/opac_openbdinfo/",
        params={"isbn": "9784297153496", "bibid": "BB08818020"},
        label="06g_openbd",
        extra_headers={"X-Requested-With": "XMLHttpRequest"},
    )
    p.get(
        "/opac/opac_bookplusinfo/",
        params={"isbn": "9784297153496", "bibid": "BB08818020", "lang": "0"},
        label="06g_bookplus",
        extra_headers={"X-Requested-With": "XMLHttpRequest"},
    )


# -- 07: facet apply -----------------------------------------------------------

def p07_facet_apply(p: Probe) -> None:
    """After a search, apply a facet using fc_val=<type>#@#<value>."""
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
            "kywd": "機械学習",
        },
        label="07a_search_for_facet",
    )
    if not p.last_opkey:
        return
    for params, label in [
        # datatype=10 (図書)
        ({"opkey": p.last_opkey, "lang": "0", "amode": "23", "place": "",
          "list_disp": "20", "list_sort": "6", "cmode": "0",
          "fc_val": "datatype#@#10"}, "07b_fc_datatype10"),
        # year=2025 (yearkey is sometimes ranged)
        ({"opkey": p.last_opkey, "lang": "0", "amode": "23", "place": "",
          "list_disp": "20", "list_sort": "6", "cmode": "0",
          "fc_val": "yearkey#@#2025"}, "07c_fc_year2025"),
        # publisher
        ({"opkey": p.last_opkey, "lang": "0", "amode": "23", "place": "",
          "list_disp": "20", "list_sort": "6", "cmode": "0",
          "fc_val": "fpub#@#丸善出版"}, "07d_fc_pub"),
        # multiple (datatype both 10 and 19) - sent as repeated fc_val
        ({"opkey": p.last_opkey, "lang": "0", "amode": "23", "place": "",
          "list_disp": "20", "list_sort": "6", "cmode": "0",
          "fc_val": ["datatype#@#10", "datatype#@#19"]}, "07e_fc_multi_datatype"),
        # subject
        ({"opkey": p.last_opkey, "lang": "0", "amode": "23", "place": "",
          "list_disp": "20", "list_sort": "6", "cmode": "0",
          "fc_val": "fsh#@#機械学習"}, "07f_fc_subject"),
    ]:
        p.get("/opac/opac_search/", params=params, label=label)


# -- 08: error / edge ----------------------------------------------------------

def p08a_no_opkey(p: Probe) -> None:
    """Detail without going through search first."""
    p.get(
        "/opac/opac_details/",
        params={"lang": "0", "amode": "11", "bibid": "BB08818020"},
        label="08a_detail_noopkey",
    )


def p08b_bad_bibid(p: Probe) -> None:
    p.get(
        "/opac/opac_details/",
        params={"lang": "0", "amode": "11", "bibid": "ZZ99999999"},
        label="08b_bad_bibid",
    )


def p08c_huge_disp(p: Probe) -> None:
    """Request 500 per page on a many-hit query."""
    p.get(
        "/opac/opac_search/",
        params={
            "lang": "0", "amode": "2", "cmode": "0", "smode": "1",
            "kywd1_exp": "Python", "con1_exp": "titlekey_ja",
            "file_exp": ["1"], "dpmc_exp": "all",
            "sort_exp": "6", "disp_exp": "500",
        },
        label="08c_disp500",
    )


def p08d_only_lang(p: Probe) -> None:
    """English UI (lang=1)."""
    p.get("/opac/opac_search/", params={"lang": "1"}, label="08d_landing_en")


# -- 09: extra: spellcheck trigger, authority, detail_book ---------------------

def p09a_spellcheck_misspell(p: Probe) -> None:
    """Search with a misspelled keyword to potentially trigger spellcheck."""
    p.get("/opac/opac_search/", params={
        "lang": "0", "amode": "2", "cmode": "0", "smode": "0",
        "kywd": "Pithon",  # misspell
    }, label="09a_misspell_pithon")
    if p.last_opkey:
        p.get(
            "/opac/opac_spellcheck/",
            params={"lang": "0", "opkey": p.last_opkey, "srvce": "0", "tikey": ""},
            label="09a_spellcheck_misspell",
            extra_headers={"X-Requested-With": "XMLHttpRequest"},
        )


def p09b_authority(p: Probe) -> None:
    """Author authority lookup (auid from a known detail)."""
    p.get(
        "/opac/opac_authority/",
        params={"lang": "0", "amode": "11", "auid": "AU00950057"},
        label="09b_authority_AU00950057",
    )


def p09c_detail_book(p: Probe) -> None:
    """Individual copy detail (opac_detail_book) with a known blkey."""
    p.get(
        "/opac/opac_detail_book/",
        params={"lang": "0", "amode": "11", "blkey": "19200695"},
        label="09c_detail_book_19200695",
    )


def p09d_blstat(p: Probe) -> None:
    """Loan status of a single copy."""
    p.get("/opac/opac_blstat/", params={
        "lang": "0", "phasecd": "50", "hldstat": "1", "lkcd": "1",
        "blipkey": "BL19200695", "prlndflg": "0", "blcd": "1",
        "odrno": "OT00477489", "bbcd": "1", "contcd": "",
        "addmsg": "返却期限",
    }, label="09d_blstat", extra_headers={"X-Requested-With": "XMLHttpRequest"})


def p09e_serial_search(p: Probe) -> None:
    """Search for a journal (datatype=20?) via file_exp=3."""
    p.get("/opac/opac_search/", params={
        "lang": "0", "amode": "2", "cmode": "0", "smode": "1",
        "kywd1_exp": "Nature", "con1_exp": "titlekey_ja",
        "file_exp": ["3"], "dpmc_exp": "all",
        "sort_exp": "6", "disp_exp": "20",
    }, label="09e_serial_nature")


REGISTRY: dict[str, tuple[Callable[[Probe], None], str]] = {
    "01_landing": (p01_landing, "Fetch landing page"),
    "02a_simple_hit": (p02_simple_search_hit, "Simple search with kywd"),
    "02b_simple_zero": (p02b_simple_search_zero, "Zero-hit simple search"),
    "02c_simple_isbn": (p02c_simple_search_isbn, "Simple search ISBN"),
    "03a_adv_title": (p03a_adv_title, "Advanced title"),
    "03b_pagination": (p03b_adv_pagination, "Pagination (amode=22)"),
    "03c_year_range": (p03c_adv_year_range, "Year range"),
    "03d_isbn_field": (p03d_adv_isbn_field, "ISBN field"),
    "03e_three_cond": (p03e_adv_three_conditions, "Three conditions"),
    "04a_cinii_simple": (p04_cinii_simple, "CiNii simple"),
    "04b_cinii_adv": (p04b_cinii_adv, "CiNii advanced"),
    "05a_detail_book": (p05a_detail_book, "Detail page"),
    "05b_detail_ebook": (p05b_detail_ebook, "Detail ebook"),
    "05c_permalink": (p05c_detail_via_permalink, "Permalink"),
    "05d_cinii_detail": (p05d_cinii_detail, "CiNii detail"),
    "06a_suggest": (p06a_suggest, "Suggest endpoint"),
    "06b_spellcheck": (p06b_spellcheck, "Spellcheck"),
    "06c_facets": (p06c_facets, "All facet types"),
    "06d_localhold": (p06d_localhold, "Localhold POST"),
    "06e_imgoutlink": (p06e_imgoutlink, "Imgoutlink"),
    "06f_stamp": (p06f_stamp, "Stamp"),
    "06g_openbd_bookplus": (p06g_openbd_bookplus, "openBD + BookPlus"),
    "07_facet_apply": (p07_facet_apply, "Facet apply amode=23"),
    "08a_no_opkey": (p08a_no_opkey, "Detail without opkey"),
    "08b_bad_bibid": (p08b_bad_bibid, "Invalid bibid"),
    "08c_disp500": (p08c_huge_disp, "disp_exp=500"),
    "08d_lang_en": (p08d_only_lang, "English UI"),
    "09a_spell_miss": (p09a_spellcheck_misspell, "Spellcheck misspell"),
    "09b_authority": (p09b_authority, "Author authority"),
    "09c_detail_book": (p09c_detail_book, "Single copy detail"),
    "09d_blstat": (p09d_blstat, "Single copy status"),
    "09e_serial": (p09e_serial_search, "Journal search file_exp=3"),
}
