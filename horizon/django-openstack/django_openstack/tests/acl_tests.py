
from django_openstack import test
from django_openstack.acl import clean_acl, parse_acl

class AclTests(test.TestCase):

    def test_clean_acl(self):
        acl = 'item,       item'
        clean_1 = clean_acl('x-container-read', acl)
        self.assertEqual(clean_1, 'item,item')
        clean_2 = clean_acl('X-Container-Write', acl)
        self.assertEqual(clean_2, 'item,item')

    def test_clean_acl_invalid(self):
        acl = '.r:-'
        self.assertRaises(ValueError, clean_acl, 'x-container-read', acl)

    def test_clean_acl_ref_3(self):
        acl = '.r:-,.ref:*,.referer:-.example.com'
        self.assertRaises(ValueError, clean_acl, 'x-container-read', acl)
    
    def test_clean_acl_ref_4(self):
        acl = '.r:'
        self.assertRaises(ValueError, clean_acl, 'x-container-read', acl)

    def test_clean_acl_ref_5(self):
        acl = '.r:*domain.com'
        clean_1 = clean_acl('x-container-read', acl)
        self.assertEqual(clean_1, '.r:domain.com')

    def test_clean_acl_ref(self):
        acl = '   .r:*   '
        clean_1 = clean_acl('x-container-read', acl)
        self.assertEqual(clean_1, '.r:*')
        self.assertRaises(ValueError, clean_acl, 'X-Container-Write', acl)

    def test_clean_acl_ref_2(self):
        acl = '   .r:*,  bob   '
        clean_1 = clean_acl('x-container-read', acl)
        self.assertEqual(clean_1, '.r:*,bob')
        self.assertRaises(ValueError, clean_acl, 'X-Container-Write', acl)
    
    def test_parse_acl_ref(self):
        acl = '.r:*'
        ref,group = parse_acl(acl)
        self.assertEqual(group, [])
        self.assertEqual(ref, ['*'])

    def test_parse_acl_ref_2(self):
        acl = '.r:*,bob'
        ref,group = parse_acl(acl)
        self.assertEqual(group, ['bob'])
        self.assertEqual(ref, ['*'])
