import os
import sys
from dotenv import load_dotenv

load_dotenv('.env')

import cloudinary
import cloudinary.api
import psycopg2

CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
API_KEY = os.getenv('CLOUDINARY_API_KEY')
API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
DATABASE_URL = os.getenv('DATABASE_URL')

if not CLOUD_NAME or not API_KEY or not API_SECRET:
    raise RuntimeError('Cloudinary 설정이 없습니다. .env에 CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET를 채워주세요.')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL 설정이 없습니다.')

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET,
    secure=True,
)


def parse_public_id(url: str) -> str:
    try:
        after = url.split('/upload/', 1)[1]
        if after.startswith('v') and '/' in after:
            _, after = after.split('/', 1)
        return after.rsplit('.', 1)[0]
    except Exception:
        parts = url.split('/')
        return '/'.join(parts[-2:]).rsplit('.', 1)[0]


def list_cloudinary_resources(prefix: str):
    resources = []
    next_cursor = None
    while True:
        params = {
            'type': 'upload',
            'prefix': prefix,
            'max_results': 500,
        }
        if next_cursor:
            params['next_cursor'] = next_cursor
        response = cloudinary.api.resources(**params)
        resources.extend(response.get('resources', []))
        next_cursor = response.get('next_cursor')
        if not next_cursor:
            break
    return resources


def load_db_public_ids():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT image_path FROM wardrobe_items WHERE image_path IS NOT NULL")
            paths = [row[0] for row in cur.fetchall() if row[0]]
            cur.execute("SELECT avatar_url FROM users WHERE avatar_url IS NOT NULL")
            paths += [row[0] for row in cur.fetchall() if row[0]]
    cloud_prefix = f"https://res.cloudinary.com/{CLOUD_NAME}/image/upload/"
    return {parse_public_id(url) for url in paths if isinstance(url, str) and url.startswith(cloud_prefix)}


def load_db_user_ids():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email FROM users ORDER BY created_at NULLS LAST")
            return [tuple(row) for row in cur.fetchall()]


def delete_cloudinary_folder(user_id: str) -> dict:
    prefix = f"users/{user_id}/"
    return cloudinary.api.delete_resources_by_prefix(prefix, type='upload')


def main(delete: bool = False):
    db_public_ids = load_db_public_ids()
    db_users = load_db_user_ids()
    db_user_ids = {row[0] for row in db_users}
    resources = list_cloudinary_resources('users/')
    cloud_ids = {r['public_id'] for r in resources}
    cloud_user_ids = {pid.split('/')[1] for pid in cloud_ids if pid.startswith('users/')}

    orphan_ids = sorted(cloud_ids - db_public_ids)
    missing_cloud_users = sorted(db_user_ids - cloud_user_ids)
    unknown_cloud_users = sorted(cloud_user_ids - db_user_ids)

    print(f'Cloudinary resources under users/: {len(cloud_ids)}')
    print(f'Cloudinary user folders found: {len(cloud_user_ids)}')
    print(f'DB users: {len(db_user_ids)}')
    print(f'DB referenced Cloudinary public_ids: {len(db_public_ids)}')
    print(f'Orphaned Cloudinary resources not referenced by DB: {len(orphan_ids)}')
    print(f'DB user IDs without Cloudinary uploads: {len(missing_cloud_users)}')
    print(f'Cloudinary user IDs not found in DB: {len(unknown_cloud_users)}')

    if missing_cloud_users:
        print('\nDB users with no Cloudinary uploads:')
        for user_id in missing_cloud_users:
            email = next((email for uid, email in db_users if uid == user_id), '')
            print(f'  {user_id} ({email})')

    if unknown_cloud_users:
        print('\nCloudinary user IDs missing from DB:')
        for user_id in unknown_cloud_users:
            print(f'  {user_id}')

    if unknown_cloud_users and delete:
        print('\nDeleting Cloudinary folders for unknown DB users...')
        for user_id in unknown_cloud_users:
            print(f'  delete folder users/{user_id}/')
            result = delete_cloudinary_folder(user_id)
            print(f'    result: {result}')

    if not orphan_ids and not unknown_cloud_users:
        print('정상입니다. Cloudinary와 DB 간 사용자/이미지 매핑이 일치하거나, DB 사용자 중 업로드가 없는 사용자만 있습니다.')

    if not orphan_ids:
        print('정상입니다. Orphaned resource가 없습니다.')
        return

    for idx, public_id in enumerate(orphan_ids[:20], 1):
        print(f'  {idx}. {public_id}')

    if delete:
        print('\n삭제를 시작합니다...')
        chunk_size = 100
        for i in range(0, len(orphan_ids), chunk_size):
            chunk = orphan_ids[i:i + chunk_size]
            result = cloudinary.api.delete_resources(chunk, type='upload')
            print(f'  삭제된 항목 {i + 1}-{i + len(chunk)} / {len(orphan_ids)}: {result}')
        print('삭제 완료.')
    else:
        print('\n--dry-run-- 실행 중입니다. 실제 삭제를 원하면 `python make_cloudinary_cleanup.py --delete`를 사용하세요.')


if __name__ == '__main__':
    delete_flag = '--delete' in sys.argv
    main(delete=delete_flag)
