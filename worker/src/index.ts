import { Hono } from 'hono'
import { Env } from './lib/supabase'
import { smokeHandler } from './routes/smoke'

const app = new Hono<{ Bindings: Env }>()

app.get('/', (c) => c.text('Envoice Agent Worker Active'))
app.post('/smoke', smokeHandler)

export default app
