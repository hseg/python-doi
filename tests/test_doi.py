import os

import requests
try:
    import cloudscraper
except ImportError:
    cloudscraper = None
from urllib.parse import urlparse, urlunparse
from warnings import warn

import pytest

from doi import (
    validate_doi, find_doi_in_text, pdf_to_doi,
    get_real_url_from_doi
)


def simplify_url(u):
    return urlparse(u)._replace(query='', fragment='')


def resolve_redirects(u):
    # Unconditionally upgrade to https, since some resolvers seem to require it
    # If removed, it'd make sense to canonicalize in simplify_url instead to
    # prevent spurious test failures
    u = urlunparse(urlparse(u)._replace(scheme='https'))

    if cloudscraper:
        scraper = cloudscraper.create_scraper()
        return simplify_url(scraper.get(u).url)

    # Try emulating a browser to not get blocked
    h = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(u, headers=h)
    return simplify_url(resp.url)


def normalize_eq(u, v, expect_diff=False):
    if u == v:
        return True
    if not expect_diff:
        warn(f"{u} textually differs from {v}, please update the relevant case.\n"
             "Attempting to recover by resolving redirects")
    return (simplify_url(u) == simplify_url(v)
            or resolve_redirects(u) == resolve_redirects(v)
            )


@pytest.mark.net
@pytest.mark.parametrize(
    "needs_cloudscraper, urls",
    [
        (True,
         ["http://pubs.aip.org/aip/jcp/article/150/7/074102/197572/Exact-two-component-equation-of-motion-coupled",  # noqa: E501
          "http://pubs.aip.org/jcp/article/150/7/074102/197572/Exact-two-component-equation-of-motion-coupled",  # noqa: E501
          "http://aip.scitation.org/doi/10.1063/1.5081715"
         ]),
     ]
)
def test_redirect(needs_cloudscraper, urls) -> None:
    base = urls[0]
    if needs_cloudscraper and cloudscraper is None:
        pytest.skip(f"cloudscraper needed to solve CloudFlare challenge on {base}")
    for other in urls[1:]:
        assert normalize_eq(base, other, expect_diff=True)


@pytest.mark.net
def test_validate_doi() -> None:
    data = [
        ("10.1063/1.5081715",
         "https://pubs.aip.org/jcp/article/150/7/074102/197572/Exact-two-component-equation-of-motion-coupled"),  # noqa: E501
        ("10.1007%2FBF01451751",
         "http://link.springer.com/10.1007/BF01451751"),
        ("10.1103/PhysRevLett.49.57",
         "https://link.aps.org/doi/10.1103/PhysRevLett.49.57"),
        ("10.1080/14786442408634457",
         "https://www.tandfonline.com/doi/full/10.1080/14786442408634457"),
        ("10.1021/jp003647e",
         "https://pubs.acs.org/doi/10.1021/jp003647e"),
        ("10.1016/S0009-2614(97)04014-1",
         "https://linkinghub.elsevier.com/retrieve/pii/S0009261497040141"),
    ]
    for doi, url in data:
        assert normalize_eq(url, validate_doi(doi))

    for doi in ["", "asdf"]:
        try:
            validate_doi(doi)
        except ValueError as e:
            assert str(e) == "HTTP 404: DOI not found"


@pytest.mark.net
def test_get_real_url_from_doi() -> None:
    data = [
        ("10.1016/S0009-2614(97)04014-1",
         "https://www.sciencedirect.com/science/"
         "article/abs/pii/S0009261497040141"),
    ]
    for doi, url in data:
        assert normalize_eq(url, get_real_url_from_doi(doi))


def test_find_doi_in_line() -> None:
    test_data = [
        ("http://dx.doi.org/10.1063/1.881498", "10.1063/1.881498"),
        ("http://dx.doi.org/10.1063%2F1.881498", "10.1063/1.881498"),
        (2 * "qer " + "var doi = '12345/12345.3'", "12345/12345.3"),
        (2 * "qer " + "var doi = '12345/12345.3';fas", "12345/12345.3"),
        (2 * "qer " + "var DoI = 12345%2F12345.3", "12345/12345.3"),
        (2 * "qer " + "var DoI : 12345%2F12345.3", "12345/12345.3"),
        ("http://scitation.org/doi/10.1063/1.881498", "10.1063/1.881498"),
        ("org/doi(10.1063/1.881498)", "10.1063/1.881498"),
        ("/scitation.org/doi/10.1063/1.881498?234saf=34", "10.1063/1.881498"),
        ("/scitation.org/doi/10.1063/1.88149 8?234saf=34", "10.1063/1.88149"),
        ("/scitation.org/doi/10.1063/1.uniau12?as=234",
         "10.1063/1.uniau12"),
        ("https://doi.org/10.1093/analys/anw053", "10.1093/analys/anw053"),
        ("http://.scitation.org/doi/10.1063/1.mart(88)1498?asdfwer",
         "10.1063/1.mart(88)1498"),
        ("@ibook{doi:10.1002/9780470125915.ch2,", "10.1002/9780470125915.ch2"),
        ('<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements'
         '.1/"><dc:format>application/pdf</dc:format><dc:identifier>'
         "doi:10.1063/1.5079474</dc:identifier></rdf:Description>",
         "10.1063/1.5079474"),
        ("<(DOI:10.1002/9780470915.CH2)/S/URI,", "10.1002/9780470915.CH2"),
        ("URL<(DOI:10.1002/9780470125915.CH2,", "10.1002/9780470125915.CH2"),
        (r"A<</S/URI/URI(https://doi.org/10.1016/j.comptc.2018.10.004)>>/"
         r"Border[0 0 0]/M(D:20181022082356+0530)/Rect[147.40158 594.36926"
         r"347.24957 605.36926]/Subtype/Link/Type/A",
         "10.1016/j.comptc.2018.10.004"),
        ("doi(10.1038/s41535-018-0103-6;)", "10.1038/s41535-018-0103-6"),
    ]
    for url, doi in test_data:
        assert find_doi_in_text(url) == doi


def test_doi_from_pdf() -> None:
    f = os.path.join(os.path.dirname(__file__), "resources", "doc.pdf")

    assert os.path.exists(f)
    assert pdf_to_doi(f) == "10.1103/PhysRevLett.50.1998"
