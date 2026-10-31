import os
import time
from pathlib import Path
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoAlertPresentException

if os.environ.get('OPENLABS3D_QA_ISOLATED') != 'yes':
    raise SystemExit('Set OPENLABS3D_QA_ISOLATED=yes only for an isolated test instance; this script creates users and orders.')
BASE=os.environ['OPENLABS3D_QA_URL'].rstrip('/')+'/'
ADMIN_EMAIL=os.environ['OPENLABS3D_QA_ADMIN_EMAIL']
ADMIN_PASSWORD=os.environ['OPENLABS3D_QA_ADMIN_PASSWORD']
options=Options(); options.add_argument('-headless'); options.set_capability('webSocketUrl',True); options.set_capability('unhandledPromptBehavior','accept')
d=webdriver.Firefox(service=Service(),options=options)
wait=WebDriverWait(d,15)
javascript_errors=[]
failed_responses=[]
fetch_errors=[]
d.script.add_javascript_error_handler(lambda event: javascript_errors.append(str(event.text)))
def observe_response(event):
    response=event.response or {}
    status=response.get('status',0)
    url=response.get('url','')
    if status>=400 and not (status==401 and '/api/auth/me' in url): failed_responses.append((status,url))
d.network.add_event_handler('response_completed',observe_response)
d.network.add_event_handler('fetch_error',lambda event: fetch_errors.append(str(event.error_text)))

def route(hash_value, selector):
    d.get(BASE+'#'+hash_value)
    return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,selector)))
def fill(selector, value):
    node=wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,selector)))
    node.clear(); node.send_keys(value)
def click(selector): wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,selector))).click()
def text_has(value): wait.until(lambda _:value.lower() in d.find_element(By.TAG_NAME,'body').text.lower())
def confirm():
    # Firefox may already have accepted the prompt when BiDi monitoring is enabled.
    try: d.switch_to.alert.accept()
    except NoAlertPresentException: pass
def register(email, name):
    route('account','#real-register')
    fill('#real-register [name=display_name]',name); fill('#real-register [name=email]',email); fill('#real-register [name=password]','Testing password 2026!')
    click('#real-register button'); wait.until(lambda _:d.current_url.endswith('#my-listings'))
def login(email,password):
    route('account','#real-login'); fill('#real-login [name=email]',email);fill('#real-login [name=password]',password)
    click('#real-login button');wait.until(lambda _:d.current_url.endswith('#my-listings'))
def logout(): route('account','#profile-form');click('#profile-form button[type=button]');wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,'#real-login')))

try:
    route('home','.hero')
    for width in (1440,768,390):
        d.set_window_size(width,900); time.sleep(.4)
        overflow=d.execute_script('return document.documentElement.scrollWidth > document.documentElement.clientWidth')
        print('responsive',width,'overflow',overflow,flush=True)
        d.save_screenshot(f'/tmp/openlabs3d-home-{width}.png')
    d.set_window_size(1440,900)
    suffix=str(int(time.time()))
    host_email=f'qa-host-{suffix}@example.org'; buyer_email=f'qa-buyer-{suffix}@example.org'; product_name=f'Browser QA tube rack {suffix}'; host_name=f'Browser QA workshop {suffix}'
    register(host_email,'Browser QA Host')
    route('onboarding','#host-application')
    values={'name':host_name,'contact':'qa@example.org','country':'Italy','region':'Turin','printers':'Printer A','technologies':'FDM','materials':'PETG','dimensions':'200 x 200 x 200 mm','capabilities':'Small batches'}
    for name,value in values.items(): fill(f'#host-application [name={name}]',value)
    click('#host-application [value=submit]');text_has('pending');print('host application submitted',flush=True)
    logout(); login(ADMIN_EMAIL,ADMIN_PASSWORD)
    route('admin/pending','.ops-nav');text_has(host_name)
    block=d.find_element(By.XPATH,f"//article[.//h3[text()='{host_name}']]")
    block.find_element(By.XPATH,".//button[text()='Approve']").click();confirm();wait.until(lambda _:not d.find_elements(By.XPATH,f"//h3[text()='{host_name}']"));print('host approved',flush=True)
    for page in ('admin','admin/products','admin/hosts','admin/orders','admin/users','admin/categories','admin/settings','admin/activity'):
        route(page,'.ops-nav')
        assert 'Unable to load this page' not in d.find_element(By.TAG_NAME,'body').text
    d.set_window_size(390,900);route('admin','.ops-nav');time.sleep(.3)
    print('admin mobile overflow',d.execute_script('return document.documentElement.scrollWidth > document.documentElement.clientWidth'),flush=True)
    d.save_screenshot('/tmp/openlabs3d-admin-390.png');d.set_window_size(1440,900)
    logout();login(host_email,'Testing password 2026!')
    route('create-listing','#listing-form')
    for name,value in {'title':product_name,'price':'12.50','material':'PETG','dimensions':'40 x 30 mm','compatibility':'Microtubes','description':'A test rack for the isolated browser workflow.'}.items():fill(f'#listing-form [name={name}]',value)
    d.find_element(By.CSS_SELECTOR,'#listing-form [name=category]').send_keys('Tube racks')
    img=Path(__file__).resolve().parents[1]/'assets/brand/openlabs3d-logo.png'
    d.find_element(By.ID,'listing-files').send_keys(str(img));click('#listing-form [value=submit]');wait.until(lambda _:d.current_url.endswith('#my-listings'));text_has('Pending approval')
    d.refresh();text_has(product_name);print('listing and photo submitted',flush=True)
    logout();login(ADMIN_EMAIL,ADMIN_PASSWORD)
    route('admin/pending','.ops-nav');text_has(product_name)
    panel=d.find_element(By.XPATH,f"//article[contains(@class,'panel') and .//h3[text()='{product_name}']]")
    panel.find_element(By.XPATH,".//button[text()='Approve']").click();confirm();wait.until(lambda _:not d.find_elements(By.XPATH,f"//h3[text()='{product_name}']"));print('listing approved',flush=True)
    logout();register(buyer_email,'Browser QA Buyer')
    route('catalogue','#filters');fill('#filters [name=q]',product_name);click('#filters .searchbar button');text_has(product_name)
    click('#results .card');wait.until(EC.presence_of_element_located((By.ID,'real-configure')));text_has('12.50')
    assert d.find_element(By.ID,'gallery-main').get_attribute('naturalWidth')!='0'
    click('#real-configure button');route('basket','#order-form');fill('#order-form [name=contact]','QA Laboratory, qa@example.org');fill('#order-form [name=address]','Test Street 1, Turin');click('#order-form button');wait.until(lambda _:d.current_url.endswith('#orders'));text_has(product_name);print('buyer order placed',flush=True)
    logout();login(host_email,'Testing password 2026!');route('host','.wrap');text_has(product_name)
    for label in ('Accept job','Mark printing','Mark ready','Mark completed'):
        wait.until(EC.element_to_be_clickable((By.XPATH,f"//button[normalize-space()='{label}']"))).click();confirm();time.sleep(.4)
    text_has('completed');print('job completed',flush=True)
    logout();login(buyer_email,'Testing password 2026!');route('orders','.wrap');text_has('completed');print('buyer sees completed status',flush=True)
    time.sleep(.5)
    unexpected_fetch_errors=[e for e in fetch_errors if 'NS_BINDING_ABORTED' not in e]
    print('browser JavaScript errors:',javascript_errors,flush=True)
    print('unexpected HTTP errors:',failed_responses,flush=True)
    print('unexpected network errors:',unexpected_fetch_errors,flush=True)
    assert not javascript_errors and not failed_responses and not unexpected_fetch_errors
except Exception:
    print('browser JavaScript errors at failure:',javascript_errors,flush=True)
    print('unexpected HTTP errors at failure:',failed_responses,flush=True)
    print('network errors at failure:',fetch_errors,flush=True)
    d.save_screenshot('/tmp/openlabs3d-browser-failure.png')
    raise
finally:
    d.quit()
