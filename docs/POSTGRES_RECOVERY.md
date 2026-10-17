# PostgreSQL / Supabase recovery

The existing Administration backup screen supports PostgreSQL. It encrypts a custom-format `pg_dump` of the `public` schema together with EduScan's local encryption key, application secret, face files, models, and templates. Supabase-managed schemas such as `auth` and `storage` are outside this application backup.

Install PostgreSQL client tools compatible with the database server. EduScan searches PATH and standard Windows PostgreSQL installation folders; alternatively set `EDUSCAN_POSTGRES_BIN` to the client `bin` folder. Credentials come from `DATABASE_URL` and are passed to tools through their environment, never process arguments. Use the configured SSL connection settings and a session or direct connection rather than a transaction pooler.

Create an encrypted backup in the existing Administration screen. Keep its passphrase separately and retain an off-device copy. Creating or downloading a backup does not alter school records.

Restore only as an explicitly authorized recovery operation:

1. In Administration, verify and stage the `.edubak` file using its passphrase and the existing confirmation field.
2. Stop EduScan and every other scanner using that database. Restarting alone never applies a PostgreSQL restore.
3. Run `scripts/apply-postgres-restore.ps1`. It requests an explicit confirmation and a new passphrase for a fresh safety backup before replacing anything.
4. The tool verifies staged hashes, creates the safety backup, and restores the PostgreSQL objects in one transaction. A database import error rolls that transaction back and leaves local face files untouched.
5. After a successful database restore, the tool preserves previous local files and the staged dump under `pre_restore_*`, then installs the matching encryption artifacts. If a local file operation fails, keep the safety backup and recovery folders and complete recovery before starting scanners.
6. Start EduScan and verify admin/teacher sign-in, student counts, a known class record, and the restored face model before resuming attendance.

The legacy MAPEH deletion scripts are now read-only previews. They require an explicit database target (`EDUSCAN_MAINTENANCE_DATABASE_URL` or `--database-url`) and never delete records. The one-off student and grading-weight update scripts are disabled; use the authorized application workflows instead.
