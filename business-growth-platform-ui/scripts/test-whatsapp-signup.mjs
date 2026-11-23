import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import ts from 'typescript'

const source = (await readFile(new URL('../src/lib/whatsapp.ts', import.meta.url), 'utf8'))
  .replace("import { request } from './api'", 'const request = globalThis.signupTestRequest')
let requests = []
globalThis.signupTestRequest = async (path, options) => { requests.push(JSON.parse(options.body)); return {id: 'test-connection'} }
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
const {connectMeta} = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'))
let listener, callback, launch
globalThis.window = {
  FB: {login(cb, options) { callback = cb; launch = options }},
  addEventListener(_, cb) { listener = cb },
  removeEventListener() { listener = undefined },
}
const event = (name, data, origin = 'https://www.facebook.com') => listener?.({origin, data: {type: 'WA_EMBEDDED_SIGNUP', event: name, data}})
const status = {config_id: 'test-config'}

const coexistence = connectMeta(status, 'test-state', undefined, 'coexistence')
assert.equal(launch.extras.featureType, 'whatsapp_business_app_onboarding')
callback({authResponse: {code: 'test-code'}})
event('FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING', {waba_id: '789'})
await coexistence
assert.equal(requests[0].connection_mode, 'coexistence')
assert.equal(requests[0].registration_pin, null)
assert.equal(requests[0].phone_number_id, undefined)

requests = []
const standard = connectMeta(status, 'test-state', '123456', 'new_number')
assert.equal(launch.extras.featureType, undefined)
event('FINISH', {waba_id: '789', phone_number_id: '456'}, 'https://attacker.example')
callback({authResponse: {code: 'test-code'}})
assert.equal(requests.length, 0)
event('FINISH', {waba_id: '789', phone_number_id: '456'})
await standard
assert.equal(requests[0].registration_pin, '123456')

requests = []
const cancelled = connectMeta(status, 'test-state', undefined, 'coexistence')
const lateCallback = callback
event('CANCEL', {})
await assert.rejects(cancelled, /cancelled/)
lateCallback({authResponse: {code: 'test-code'}})
assert.equal(requests.length, 0)
console.log('WhatsApp signup: coexistence without phone ID, new-number PIN, origin filtering and cancellation passed.')
