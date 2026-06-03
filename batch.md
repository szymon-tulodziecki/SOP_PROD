# Batch deploy

Pakujesz plik(i) tarem → wysyłasz `pscp` → rozpakowujesz na serwerze i restartujesz kontener.

## Raz na sesję PowerShella

```powershell
$P = Read-Host -AsSecureString "Hasło SSH" | ConvertFrom-SecureString -AsPlainText
$H = "ip-serwera"
cd C:\Users\Szymon\Desktop\Repozytoria\SOP_PROD
```

## Każdy deploy

```powershell
tar -czf $env:TEMP\batch.tar.gz `
  app_admin/templates/zarzadzanie/firmy/formularz.html

pscp -P 25666 -pw $P -batch $env:TEMP\batch.tar.gz sop@${H}:/tmp/batch.tar.gz

plink -P 25666 -pw $P -batch sop@$H "cd ~/sop_prod && tar -xzf /tmp/batch.tar.gz && docker restart sop_admin && rm -f /tmp/batch.tar.gz"
```

Podmieniasz tylko **listę plików** w `tar` i **kontener** w `docker restart`.

## Który kontener restartować

| Zmieniłeś | `docker restart …` |
|---|---|
| `app_admin/**` | `sop_admin` |
| `app_student/**` | `sop_student` |
| `core/**` | `sop_admin sop_student` |
| `nginx/nginx.conf` | `sop_nginx` |

Jak zmieniłeś `.env` lub `docker-compose.yml` — wtedy zamiast `docker restart`:
```
cd ~/sop_prod && docker compose up -d
```

## Zasady

- Pakuj **z korzenia repo** (`SOP_PROD\`), ścieżki dokładnie jak w repo, ze slashami `/`.
- Hasła i IP **nie wpisuj** inline — zawsze przez `$P` i `$H`.
