// Run with a path to an installed @electric-sql/pglite package as argument 2.
const {PGlite} = require(process.argv[2]);
const {readFileSync} = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async()=>{
 const db = new PGlite();
 const ws='11111111-1111-4111-8111-111111111111';
 const other='22222222-2222-4222-8222-222222222222';
 const holder='33333333-3333-4333-8333-333333333333';
 await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
 create schema auth;create table auth.users(id uuid primary key);
 create schema storage;create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
 create table public.workspaces(id uuid primary key);
 create table public.workspace_members(workspace_id uuid,user_id uuid,role text);
 insert into auth.users values('${ws}'),('${other}');
 insert into workspaces values('${ws}'),('${other}');
 insert into workspace_members values('${ws}','${ws}','owner'),('${other}','${other}','owner');`);
 await db.exec(readFileSync(path.join(__dirname,'../supabase/migrations/20261121192057_growboard_google_workspace.sql'),'utf8'));
 async function scalar(sql,params=[]){return Object.values((await db.query(sql,params)).rows[0])[0]}
 await db.query('select gbp_save_connection($1,$1,$2,$3,$4,$5)',[ws,'google-sub','test@example.test','encrypted',['business.manage']]);
 await db.query('select gbp_save_connection($1,$1,$2,$3,$4,$5)',[other,'other-sub','other@example.test','encrypted',['business.manage']]);
 await assert.rejects(db.query('select gbp_save_connection($1,$2,$3,$4,$5,$6)',[ws,other,'steal','x','x',[]]));
 assert.equal(await scalar('select gbp_register_location($1,$2,$3,$4,$5,$6)',['accounts/a/locations/l',ws,'Shop','accounts/a','Account',{}]),true);
 assert.equal(await scalar('select gbp_register_location($1,$2,$3,$4,$5,$6)',['accounts/a/locations/l',other,'Stolen','accounts/a','Account',{}]),false);
 await assert.rejects(db.query('select gbp_register_location($1,$2,$3,$4,$5,$6)',['accounts/other/locations/l',other,'Stolen alias','accounts/other','Account',{}]));
 await db.exec(readFileSync(path.join(__dirname,'../supabase/migrations/20261122073705_growboard_rank_keyword_priorities.sql'),'utf8'));
 await db.query(`insert into gbp_rank_keyword_sets(workspace_id,location_name,keywords)values($1,'accounts/a/locations/l',$2)`,[ws,JSON.stringify(['preschool','daycare'])]);
 assert.deepEqual(await scalar(`select keywords from gbp_rank_keyword_sets where workspace_id=$1`,[ws]),['preschool','daycare']);
 await assert.rejects(db.query(`update gbp_rank_keyword_sets set keywords=$1`,[JSON.stringify(Array(11).fill('phrase'))]));
 assert.equal(await scalar(`select has_table_privilege('authenticated','gbp_rank_keyword_sets','SELECT')`),false);
 assert.equal(await scalar(`select has_table_privilege('anon','gbp_rank_keyword_sets','INSERT')`),false);
 assert.equal(await scalar(`select relrowsecurity from pg_class where relname='gbp_rank_keyword_sets'`),true);
 await db.query(`insert into gbp_oauth_states(state_hash,workspace_id,user_id,verifier_cipher)values('once',$1,$1,'encrypted')`,[ws]);
 assert.equal((await db.query(`select * from gbp_consume_oauth_state('once')`)).rows.length,1);
 assert.equal((await db.query(`select * from gbp_consume_oauth_state('once')`)).rows.length,0);
 await db.query(`insert into gbp_review_rules(location_name,workspace_id,enabled,enabled_at,enabled_by,delivery_owned,mode,daily_limit)
 values('accounts/a/locations/l',$1,true,now(),$1,true,'auto_publish',1)`,[ws]);
 const ids=[];
 for(const name of ['one','two']){
  ids.push(await scalar(`insert into gbp_review_jobs(workspace_id,location_name,review_name,review_data,reply_text,status)
   values($1,'accounts/a/locations/l',$2,'{}','Thanks','ready')returning id`,[ws,'accounts/a/locations/l/reviews/'+name]));
 }
 assert.equal(await scalar('select gbp_claim_reply($1,$2)',[ids[0],holder]),true);
 assert.equal(await scalar('select gbp_claim_reply($1,$2)',[ids[0],holder]),false,'same reply cannot be claimed twice');
 assert.equal(await scalar('select gbp_claim_reply($1,$2)',[ids[1],holder]),false,'pending reservations consume daily quota');
 await db.query(`update gbp_review_jobs set status='uncertain' where id=$1`,[ids[0]]);
 assert.equal(await scalar('select gbp_claim_reply($1,$2)',[ids[0],holder]),false,'uncertain delivery is held');
 await db.query(`update gbp_review_rules set enabled=false where workspace_id=$1`,[ws]);
 await db.query(`update gbp_review_jobs set reserved_on=null where id=$1`,[ids[0]]);
 assert.equal(await scalar('select gbp_claim_reply($1,$2)',[ids[1],holder]),false,'pause blocks delivery');
 await db.query('select gbp_disconnect($1)',[ws]);
 assert.equal(await scalar('select refresh_token_cipher is null from gbp_connections where workspace_id=$1',[ws]),true);
 assert.equal(await scalar('select status from gbp_review_jobs where id=$1',[ids[1]]),'cancelled');
 await db.query('select gbp_save_connection($1,$1,$2,$3,$4,$5)',[ws,'google-sub','test@example.test','encrypted',['business.manage']]);
 await db.query('select gbp_register_location($1,$2,$3,$4,$5,$6)',['accounts/a/locations/l',ws,'Shop','accounts/a','Account',{}]);
 const campaign='44444444-4444-4444-8444-444444444444';
 await assert.rejects(db.query('select gbp_create_campaign($1,$2,$3,$4,$5,$6)',[ws,campaign,'Must rollback','Asia/Kolkata',['accounts/a/locations/l','accounts/a/locations/foreign'],{}]));
 assert.equal(Number(await scalar('select count(*) from gbp_campaigns')),0,'invalid target rolls back whole campaign');
 await db.query('select gbp_create_campaign($1,$2,$3,$4,$5,$6)',[ws,campaign,'Campaign','Asia/Kolkata',['accounts/a/locations/l'],{summary:'Hello'}]);
 assert.equal(await scalar('select gbp_control_campaign($1,$2,$3,null)',[other,campaign,'cancel']),false);
 assert.equal(await scalar('select gbp_control_campaign($1,$2,$3,now()+interval \'1 day\')',[ws,campaign,'schedule']),true);
 await db.query(`update gbp_posts set scheduled_for=now()-interval '1 second' where campaign_id=$1`,[campaign]);
 const postId=await scalar('select id from gbp_posts where campaign_id=$1',[campaign]);
 assert.equal(await scalar('select gbp_claim_post($1)',[postId]),true);
 assert.equal(await scalar('select gbp_claim_post($1)',[postId]),false);
 assert.equal(await scalar('select gbp_control_campaign($1,$2,$3,null)',[ws,campaign,'cancel']),false,'claimed campaign cannot be cancelled');
 const tables=(await db.query(`select relname from pg_class join pg_namespace n on n.oid=relnamespace where n.nspname='public' and relname like 'gbp_%' and relkind='r'`)).rows;
 for(const {relname} of tables){
  assert.equal(await scalar(`select relrowsecurity from pg_class where oid=$1::regclass`,[relname]),true);
  assert.equal(await scalar(`select has_table_privilege('authenticated',$1,'SELECT')`,[relname]),false);
 }
 assert.equal(await scalar(`select has_function_privilege('authenticated','gbp_claim_reply(uuid,uuid)','EXECUTE')`),false);
 await db.close();
 console.log('Google schema: ownership, replay, quota, pause, disconnect and backend-only permissions passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
