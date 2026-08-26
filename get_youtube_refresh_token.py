"""
get_youtube_refresh_token.py
=============================
سكريبت خدامه مرة وحدة فقط، تديرو محليا فالكمبيوتر ديالك (ماشي فـ GitHub Actions)
باش تجيب "Refresh Token" ديال يوتيوب. هاد التوكن ما كيتنتهيش (خلاف التوكنات
العاديين)، وغادي تحطو فـ GitHub Secrets وتنساه.

طريقة الاستعمال:
1. pip install google-auth-oauthlib
2. حط ملف client_secret.json (اللي حملتيه من Google Cloud Console) فنفس المجلد
3. python get_youtube_refresh_token.py
4. غادي يحل ليك المتصفح، دخل بحساب يوتيوب/جوجل اللي فيه القناة، ووافق
5. الـ Refresh Token غادي يبان ليك فالـ Terminal، انسخو لـ GitHub Secrets
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = "client_secret.json"

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
credentials = flow.run_local_server(port=8080)

print("\n" + "=" * 60)
print("✅ خدمة! هاكوما القيم اللي خاصك تزيدهم فـ GitHub Secrets:")
print("=" * 60)
print(f"YT_CLIENT_ID = {credentials.client_id}")
print(f"YT_CLIENT_SECRET = {credentials.client_secret}")
print(f"YT_REFRESH_TOKEN = {credentials.refresh_token}")
print("=" * 60)
