from app.sanitize import clean,credential,defang,domain,public_ip


def test_controls_and_ansi():
    assert clean('\x1b[31mred\x1b[0m\x00\n\u202e')=='red'
    assert len(clean('x'*10000,100))==100


def test_credential_masking():
    assert credential('x'*65)=='[masked]'
    assert credential('ghp_12345678901234567890')=='[masked]'
    assert credential('Ab9xK2mQ5pT7vR3nL6wZ')=='[masked]'
    assert credential('password')=='password'
    assert clean('<script>alert(1)</script>')=='<script>alert(1)</script>'
    assert credential('<script>alert(1)</script>')=='[masked]'


def test_defanging():
    assert defang('curl https://evil.example/a')=='curl hxxps://evil[.]example/a'
    assert domain('http://[broken')==''
    assert public_ip('1.2.3.4',True)=='1.2.3.0/24'
    assert public_ip('2001:db8:abcd::1',True)=='2001:db8:abcd::/48'
