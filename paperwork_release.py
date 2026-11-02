"""Versioned simulation releases and per-pilot serialization for the single-process server."""
import copy,functools,hashlib,json,threading,time
_LOCKS=[threading.RLock() for _ in range(64)]
def serialized(fn):
 @functools.wraps(fn)
 def wrapper(*args,**kwargs):
  import va
  pid=(kwargs.get('pid') or (args[0] if args and fn.__name__=='check_ofp_watch' else None) or va.current_pilot_id())
  with _LOCKS[int(hashlib.sha256(str(pid).encode()).hexdigest()[:8],16)%len(_LOCKS)]:
   return fn(*args,**kwargs)
 return wrapper

def revision(booking):
 d=copy.deepcopy(booking.get('dispatch') or {})
 for key in ('signed','signed_snapshot'):d.pop(key,None)
 body={k:booking.get(k) for k in ('requested_at','flight_number','aircraft','airframe','mission','ofp')}
 body['dispatch']=d
 return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()

def valid_signature(booking):
 s=booking.get('signed') or {}
 return bool(s.get('revision')==revision(booking) and (not (booking.get('dispatch') or {}).get('dg') or s.get('notoc') is True))

def invalidate(booking):
 if booking.pop('signed',None):booking['release_amended']=True
 d=booking.get('dispatch') or {}
 d.pop('signed',None);d.pop('signed_snapshot',None)

def sign(booking,body,pilot):
 if not isinstance(body,dict) or body.get('requested_at')!=booking.get('requested_at') or body.get('revision')!=revision(booking):
  return 'This release changed. Reload the paperwork and review the latest revision.',409
 if body.get('reviewed') is not True:return 'Confirm that you reviewed the release.',400
 d=booking.get('dispatch') or {}
 if not d:return 'Generate the dispatch release before signing.',409
 if d.get('dg') and body.get('notoc') is not True:return 'Confirm receipt of the NOTOC.',400
 s={'at':time.time(),'by':pilot['name'],'id':pilot['id'],'revision':revision(booking),'notoc':bool(d.get('dg'))}
 snapshot={'dispatch':copy.deepcopy(d),'ofp':copy.deepcopy(booking.get('ofp'))}
 snapshot['dispatch'].pop('signed',None);snapshot['dispatch'].pop('signed_snapshot',None)
 booking['signed']=s;booking.pop('release_amended',None)
 d['signed']=s;d['signed_snapshot']=snapshot
 return None,200

def started(booking):
 marker=booking.get('release_start') or {}
 return bool(marker.get('requested_at')==booking.get('requested_at') and marker.get('at'))

def mark_started(booking):
 booking['release_start']={'requested_at':booking.get('requested_at'),'at':time.time(),'revision':revision(booking)}
