import postgres from 'postgres'

export function resolveDatabaseSsl(mode = process.env.DATABASE_SSL_MODE): false | 'require' {
  return mode?.trim().toLowerCase() === 'disable' ? false : 'require'
}

// TLS is fail-closed by default. The bundled private Postgres network must opt
// out explicitly because that service does not terminate TLS.
const sql = process.env.DATABASE_URL
  ? postgres(process.env.DATABASE_URL, {
      ssl: resolveDatabaseSsl(),
    })
  : null

export default sql
