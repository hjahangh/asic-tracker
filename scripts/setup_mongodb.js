// Run with mongosh --nodb --quiet --file scripts/setup_mongodb.js.
// Credentials come from environment variables or protected *_FILE paths.
// The hosting DBA runs this; the application never receives admin credentials.
'use strict';
const fs = require('fs');
function secret(name) {
  if (process.env[name] !== undefined && process.env[name + '_FILE']) throw new Error('Conflicting secret inputs');
  return process.env[name + '_FILE'] ? fs.readFileSync(process.env[name + '_FILE'], 'utf8').trim() : process.env[name];
}
function required(name) {
  const value = secret(name);
  if (!value) throw new Error('Missing required setup input');
  return value;
}
function sameRoles(actual, expected) {
  const normalized = values => values.map(x => x.db + ':' + x.role).sort().join('|');
  return normalized(actual) === normalized(expected);
}
try {
  const databaseName = required('MONGODB_DATABASE');
  const ownerName = required('MONGODB_OWNER_USER');
  const runtimeName = required('MONGODB_RUNTIME_USER');
  const ownerPassword = required('MONGODB_OWNER_PASSWORD');
  const runtimePassword = required('MONGODB_RUNTIME_PASSWORD');
  if (!/^[A-Za-z0-9_-]{1,63}$/.test(databaseName) || ownerName === runtimeName ||
      !/^[A-Za-z0-9_-]{1,80}$/.test(ownerName) || !/^[A-Za-z0-9_-]{1,80}$/.test(runtimeName) ||
      ownerPassword.length < 32 || runtimePassword.length < 32) throw new Error('Invalid database or user inputs');
  const connection = new Mongo(required('MONGODB_ADMIN_URI'));
  const admin = connection.getDB('admin');
  if (process.env.MONGODB_INIT_REPLICA_SET === 'true') {
    // Only the disposable/local template enables this. Production topology is DBA-managed.
    const member = required('MONGODB_REPLICA_MEMBER');
    const name = process.env.MONGODB_REPLICA_SET || 'tracker-rs';
    let status;
    try {status = admin.runCommand({replSetGetStatus: 1});}
    catch (error) {
      if (error.code !== 94) throw error;
      status = {ok: 0, code: 94};
    }
    if (status.ok !== 1 && status.code === 94) {
      const initiated = admin.runCommand({replSetInitiate: {_id: name, members: [{_id: 0, host: member}]}});
      if (initiated.ok !== 1) throw new Error('Replica set initialization failed');
    } else if (status.ok !== 1 || status.set !== name) throw new Error('Unexpected replica set');
    let primary = false;
    for (let attempt = 0; attempt < 150; attempt++) {
      if (admin.runCommand({hello: 1}).isWritablePrimary) {primary = true; break;}
      sleep(200);
    }
    if (!primary) throw new Error('Replica set election timed out');
  }
  const hello = admin.runCommand({hello: 1});
  if (!hello.setName && hello.msg !== 'isdbgrid') throw new Error('Transactions require a replica set or sharded cluster');
  const application = connection.getDB(databaseName);
  const mutableCollections = ['business_entity', 'funding_source', 'project_family', 'project', 'asic',
    'planning_event', 'forecast_version', 'forecast_line', 'recovery_snapshot', 'snapshot_chunk'];
  const privileges = [
    {resource: {db: databaseName, collection: ''}, actions: ['listCollections', 'listIndexes']},
    ...mutableCollections.map(collection => ({resource: {db: databaseName, collection}, actions: ['find', 'insert', 'update', 'remove']})),
    {resource: {db: databaseName, collection: 'workspace_meta'}, actions: ['find', 'update']},
    {resource: {db: databaseName, collection: 'audit_entry'}, actions: ['find', 'insert']},
    {resource: {db: databaseName, collection: 'audit_chunk'}, actions: ['find', 'insert']},
  ];
  const roleName = 'asicTrackerRuntime';
  if (application.getRole(roleName)) application.updateRole(roleName, {privileges, roles: []});
  else application.createRole({role: roleName, privileges, roles: []});
  const ensureUser = (user, pwd, roles) => {
    const existing = application.getUser(user);
    if (existing) {
      if (!sameRoles(existing.roles, roles)) throw new Error('Existing account has unexpected roles; DBA review required');
      // Never rotate an existing password as an incidental startup operation.
    } else application.createUser({user, pwd, roles});
  };
  ensureUser(ownerName, ownerPassword, [{role: 'readWrite', db: databaseName}, {role: 'dbAdmin', db: databaseName}]);
  ensureUser(runtimeName, runtimePassword, [{role: roleName, db: databaseName}]);
  print('MongoDB application roles/users are ready. Existing passwords were left unchanged.');
} catch (_) {
  // Driver errors can include URI material; do not print exception details or credentials.
  print('MongoDB setup failed. Check protected inputs, admin access, replica-set configuration and dedicated user roles.');
  quit(1);
}
