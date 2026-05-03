from supabase import Client, create_client

from app.config.settings import settings


def create_supabase_client(use_service_role: bool = True) -> Client:
    """
    Cria um cliente Supabase.

    :param use_service_role: Se True, usa a Service Role Key (ignora RLS, acesso total).
                             Se False, usa a Anon Key (respeita RLS, acesso restrito).
    """
    url: str = settings.SUPABASE_URL

    if use_service_role:
        key: str = settings.SUPABASE_SERVICE_ROLE_KEY
    else:
        key: str = settings.SUPABASE_ANON_KEY

    return create_client(url, key)


supabase_admin = create_supabase_client(use_service_role=True)
supabase_anon = create_supabase_client(use_service_role=False)
