package com.dial.van.queue;

import android.content.SharedPreferences;
import kotlin.jvm.functions.Function0;
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.*;
import java.lang.reflect.*;
import java.nio.file.*;
import java.io.*;
import java.security.*;
import java.security.cert.Certificate;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.spec.SecretKeySpec;

/**
 * SOURCE tests execute the production EncryptedCommandQueue, including AES-GCM,
 * serialization, index writes and original operation recovery. Only Android's
 * native Keystore/SharedPreferences boundary and constructor initialization are
 * host fixtures. These tests do not qualify Android native storage or hardware.
 */
public class QueueRestorationActualStoreTest {
    public static class FixtureKeyStore extends KeyStoreSpi {
        public Key engineGetKey(String a,char[] p){return new SecretKeySpec(new byte[16],"AES");}
        public Certificate[] engineGetCertificateChain(String a){return null;}
        public Certificate engineGetCertificate(String a){return null;}
        public Date engineGetCreationDate(String a){return new Date(0);}
        public void engineSetKeyEntry(String a,Key k,char[] p,Certificate[] c){}
        public void engineSetKeyEntry(String a,byte[] k,Certificate[] c){}
        public void engineSetCertificateEntry(String a,Certificate c){}
        public void engineDeleteEntry(String a){}
        public Enumeration<String> engineAliases(){return Collections.enumeration(List.of("SOURCE-key"));}
        public boolean engineContainsAlias(String a){return true;}
        public int engineSize(){return 1;}
        public boolean engineIsKeyEntry(String a){return true;}
        public boolean engineIsCertificateEntry(String a){return false;}
        public String engineGetCertificateAlias(Certificate c){return null;}
        public void engineStore(OutputStream o,char[] p){}
        public void engineLoad(InputStream i,char[] p){}
        public KeyStore.Entry engineGetEntry(String a,KeyStore.ProtectionParameter p){return new KeyStore.SecretKeyEntry(new SecretKeySpec(new byte[16],"AES"));}
    }
    /** One file is the SOURCE adapter for the one canonical preferences owner. */
    static class Store implements InvocationHandler {
        final Path file;
        final Map<String,String> memory = new HashMap<>();
        int commits, failAt=-1;
        boolean persistOnFailure;
        Runnable nextSuccessfulCommit;
        CountDownLatch removalReached,continueRemoval;
        final SharedPreferences prefs=(SharedPreferences)Proxy.newProxyInstance(getClass().getClassLoader(),new Class[]{SharedPreferences.class},this);
        Store(Path file)throws Exception {
            this.file=file;
            if(Files.exists(file)){Properties p=new Properties();try(InputStream i=Files.newInputStream(file)){p.load(i);}for(String k:p.stringPropertyNames())memory.put(k,p.getProperty(k));}
        }
        public synchronized Object invoke(Object p,Method method,Object[] a)throws Throwable {
            switch(method.getName()) {
                case "getString":return memory.getOrDefault((String)a[0],(String)a[1]);
                case "getAll":return new HashMap<>(memory);
                case "contains":return memory.containsKey((String)a[0]);
                case "edit":return editor();
                default:throw new UnsupportedOperationException(method.getName());
            }
        }
        private Object editor() {
            Map<String,String> writes=new HashMap<>();Set<String> removed=new HashSet<>();
            return Proxy.newProxyInstance(getClass().getClassLoader(),new Class[]{SharedPreferences.Editor.class},(p,m,a)->{
                switch(m.getName()) {
                    case "putString":writes.put((String)a[0],(String)a[1]);return p;
                    case "remove":removed.add((String)a[0]);return p;
                    case "commit":
                        if(!removed.isEmpty()&&removalReached!=null){removalReached.countDown();if(!continueRemoval.await(5,TimeUnit.SECONDS))throw new AssertionError("SOURCE barrier timeout");}
                        synchronized(this) {
                            commits++;
                            removed.forEach(memory::remove);memory.putAll(writes);
                            boolean failed=commits==failAt;
                            if(!failed||persistOnFailure)writeDisk();
                            if(!failed&&nextSuccessfulCommit!=null){Runnable next=nextSuccessfulCommit;nextSuccessfulCommit=null;next.run();}
                            return !failed;
                        }
                    default:throw new UnsupportedOperationException(m.getName());
                }
            });
        }
        private void writeDisk()throws Exception {
            Properties properties=new Properties();properties.putAll(memory);
            Path temp=Files.createTempFile(file.getParent(),"SOURCE-prefs-",".tmp");
            try(OutputStream o=Files.newOutputStream(temp)){properties.store(o,"SOURCE canonical protected-preferences boundary fixture");}
            Files.move(temp,file,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        }
    }
    Path directory;
    Store store;
    AtomicReference<QueueOwnerScope> actor;
    EncryptedCommandQueue queue;
    static QueueOwnerScope owner(String profile,String auth){return new QueueOwnerScope(profile,"SOURCE-device",auth,System.currentTimeMillis()+600000);}
    @Before public void setup()throws Exception {
        installFixtureProvider();
        Field f=EncryptedCommandQueue.class.getDeclaredField("storeUncertain");f.setAccessible(true);f.setBoolean(null,false);
        Path base=Path.of(System.getProperty("van.queue.testBase",System.getProperty("java.io.tmpdir")+"/van-queue-restoration-source-tests"));Files.createDirectories(base);
        directory=Files.createTempDirectory(base,"SOURCE-case-");store=new Store(directory.resolve("canonical.properties"));
        actor=new AtomicReference<>(owner("SOURCE-profile","SOURCE-auth"));queue=queue(store,actor);
    }
    static void installFixtureProvider() {
        if(Security.getProvider("SOURCE-queue-test")==null)Security.addProvider(new Provider("SOURCE-queue-test",1.0,"SOURCE fixture, no native authority"){{put("KeyStore.AndroidKeyStore",FixtureKeyStore.class.getName());}});
    }
    static void set(Object object,String name,Object value)throws Exception {Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);f.set(object,value);}
    static EncryptedCommandQueue queue(Store store,AtomicReference<QueueOwnerScope> actor)throws Exception {
        Field f=Class.forName("sun.misc.Unsafe").getDeclaredField("theUnsafe");f.setAccessible(true);Object unsafe=f.get(null);
        EncryptedCommandQueue q=(EncryptedCommandQueue)unsafe.getClass().getMethod("allocateInstance",Class.class).invoke(unsafe,EncryptedCommandQueue.class);
        set(q,"indexPrefs",store.prefs);set(q,"keystoreAlias","SOURCE-key");
        Object json=Class.forName("kotlinx.serialization.json.Json").getField("Default").get(null);set(q,"json",json);set(q,"restoreJson",json);
        set(q,"currentOwner",(Function0<QueueOwnerScope>)()->actor.get());return q;
    }
    static QueuedCommand legacy(String id,String kind,long expiry)throws Exception {
        Constructor<?> constructor=Arrays.stream(QueuedCommand.class.getConstructors()).filter(c->c.getParameterTypes()[0]==String.class&&!Arrays.asList(c.getParameterTypes()).contains(kotlin.jvm.internal.DefaultConstructorMarker.class)).findFirst().orElseThrow();
        Object[] values=new Object[constructor.getParameterCount()];Class<?>[] types=constructor.getParameterTypes();
        for(int i=0;i<types.length;i++){if(types[i]==int.class)values[i]=0;else if(types[i]==long.class)values[i]=0L;else if(types[i]==boolean.class)values[i]=false;}
        values[0]=id;values[1]=id;values[2]=kind;values[3]="{\"text\":\"SOURCE\"}";values[4]="NORMAL";values[5]="A1";values[6]="NORMAL";values[7]=System.currentTimeMillis();values[8]=expiry;
        return (QueuedCommand)constructor.newInstance(values);
    }
    static QueuedCommand enqueue(EncryptedCommandQueue q,String key){return q.enqueue(new QueueEnqueueRequest(CommandKind.TASK,"{\"text\":\"SOURCE\"}",CommandSensitivity.NORMAL,ActionClass.A1,ReplayPolicy.NORMAL,key,600000));}
    static QueueRestoreResult discard(EncryptedCommandQueue q,QueueRestoreRequest r){return q.discardReviewed(r,()->false);}
    @Test public void exactUnsentBatchPreservesForeignLegacyAndNewUnselectedBytes()throws Exception {
        queue.upsert(legacy("session","SESSION_ENVELOPE",System.currentTimeMillis()+600000));queue.upsert(legacy("context","CONTEXT_INGEST",System.currentTimeMillis()+600000));queue.upsert(legacy("legacy","TASK",System.currentTimeMillis()+600000));
        String session=store.memory.get("cmd_session"),context=store.memory.get("cmd_context"),legacy=store.memory.get("cmd_legacy");
        QueuedCommand selected=enqueue(queue,"SOURCE-selected");QueueRestoreRequest request=queue.reviewDiscard();
        EncryptedCommandQueue other=queue(store,actor);QueuedCommand added=enqueue(other,"SOURCE-new");QueueRestoreResult result=discard(queue,request);
        assertEquals("APPLIED",result.getState());assertEquals(List.of(selected.getId()),result.getRemovedIds());assertFalse(result.getExternalCancellationClaimed());
        assertEquals(session,store.memory.get("cmd_session"));assertEquals(context,store.memory.get("cmd_context"));assertEquals(legacy,store.memory.get("cmd_legacy"));assertTrue(store.memory.get("index").contains(added.getId()));
        assertEquals(result,other.restoreResult(request.getOperationId()));assertEquals(result,discard(other,request));
        assertEquals(new QueueRestoreInventory(1,1,2,0),queue.restoreInventory());
    }
    @Test public void concurrentOtherInstanceEnqueueSurvivesAtomicSelectedDiscard()throws Exception {
        QueuedCommand selected=enqueue(queue,"SOURCE-selected");QueueRestoreRequest request=queue.reviewDiscard();EncryptedCommandQueue other=queue(store,actor);
        store.removalReached=new CountDownLatch(1);store.continueRemoval=new CountDownLatch(1);ExecutorService workers=Executors.newFixedThreadPool(2);
        try {
            Future<QueueRestoreResult> clearing=workers.submit(()->discard(queue,request));assertTrue(store.removalReached.await(5,TimeUnit.SECONDS));
            Future<QueuedCommand> writing=workers.submit(()->enqueue(other,"SOURCE-unselected"));Thread.sleep(30);assertFalse(writing.isDone());store.continueRemoval.countDown();
            assertEquals("APPLIED",clearing.get(5,TimeUnit.SECONDS).getState());QueuedCommand added=writing.get(5,TimeUnit.SECONDS);assertTrue(store.memory.get("index").contains(added.getId()));assertFalse(store.memory.containsKey("cmd_"+selected.getId()));
        } finally {store.continueRemoval.countDown();workers.shutdownNow();assertTrue(workers.awaitTermination(5,TimeUnit.SECONDS));}
    }
    @Test public void claimWinsRefusesDiscardAndDiscardWinsPreventsClaim()throws Exception {
        QueuedCommand first=enqueue(queue,"SOURCE-first");QueueRestoreRequest before=queue.reviewDiscard();QueuedCommand claimed=queue.claimGeneric(first.getId(),queue.genericRevision(first));assertNotNull(claimed);
        assertEquals("REFUSED",discard(queue,before).getState());assertTrue(store.memory.containsKey("cmd_"+first.getId()));
        QueuedCommand second=enqueue(queue,"SOURCE-second");QueueRestoreRequest after=queue.reviewDiscard();assertEquals(List.of(second.getId()),after.getItems().stream().map(QueueRestoreItem::getId).toList());discard(queue,after);assertNull(queue.claimGeneric(second.getId(),queue.genericRevision(second)));
    }
    @Test public void changedPendingActorRefusesButCompletedHistoryUsesCurrentStableOwner()throws Exception {
        enqueue(queue,"SOURCE-first");QueueRestoreRequest first=queue.reviewDiscard();QueueRestoreResult applied=discard(queue,first);String raw=store.memory.get("restore_operation_"+first.getOperationId());
        enqueue(queue,"SOURCE-next");QueueRestoreRequest next=queue.reviewDiscard();actor.set(owner("SOURCE-profile","SOURCE-new-auth"));
        QueueRestoreResult refused=discard(queue,next);assertEquals("queue_restore_owner_changed",refused.getReason());assertTrue(refused.getRemovedIds().isEmpty());assertEquals(applied,queue.restoreResult(first.getOperationId()));assertEquals(raw,store.memory.get("restore_operation_"+first.getOperationId()));
    }
    @Test public void profileChangeMissingAuthorityTamperAndCancellationPreserveSelectedData()throws Exception {
        QueuedCommand cmd=enqueue(queue,"SOURCE-first");QueueRestoreRequest request=queue.reviewDiscard();String raw=store.memory.get("cmd_"+cmd.getId());
        actor.set(owner("SOURCE-other-profile","SOURCE-auth"));assertThrows(IllegalStateException.class,()->discard(queue,request));actor.set(null);assertThrows(IllegalStateException.class,()->discard(queue,request));actor.set(owner("SOURCE-profile","SOURCE-auth"));
        QueueRestoreRequest tampered=new QueueRestoreRequest(request.getOperationId(),request.getOwner(),request.getItems(),request.getRevision(),request.getIssuedAtMs(),request.getDeadlineMs(),request.getRequestToken()+"A");assertThrows(Throwable.class,()->discard(queue,tampered));
        assertEquals("queue_restore_cancelled",queue.discardReviewed(request,()->true).getReason());assertEquals(raw,store.memory.get("cmd_"+cmd.getId()));
    }
    @Test public void currentnessIsRecheckedAfterDurableIntentBeforeLocalEffect()throws Exception {
        QueuedCommand cmd=enqueue(queue,"SOURCE-first");QueueRestoreRequest request=queue.reviewDiscard();store.nextSuccessfulCommit=()->actor.set(owner("SOURCE-profile","SOURCE-replaced-context"));
        assertEquals("queue_restore_owner_changed",discard(queue,request).getReason());assertTrue(store.memory.containsKey("cmd_"+cmd.getId()));
    }
    @Test public void genericCleanupPreservesExpiredForeignAndUnknownRecovery()throws Exception {
        queue.upsert(legacy("session","SESSION_ENVELOPE",1));queue.upsert(legacy("context","CONTEXT_INGEST",1));queue.upsert(legacy("legacy","TASK",1));
        Map<String,String> before=new HashMap<>(store.memory);queue.drainExecutable(System.currentTimeMillis());queue.purgeExpired(System.currentTimeMillis()+1000000);assertEquals(before,store.memory);
        QueuedCommand cmd=enqueue(queue,"SOURCE-original");QueuedCommand claim=queue.claimGeneric(cmd.getId(),queue.genericRevision(cmd));String body="{\"idempotency_key\":\"SOURCE-original\",\"device_id\":\"SOURCE-device\",\"command_id\":\"SOURCE-command\"}";
        queue.recordGenericPrepared(cmd.getId(),claim.getGenericClaimId(),body);queue.recordGenericUnknown(cmd.getId(),claim.getGenericClaimId(),"SOURCE-lost-reply");String original=store.memory.get("cmd_"+cmd.getId());queue.purgeExpired(System.currentTimeMillis()+1000000);assertEquals(original,store.memory.get("cmd_"+cmd.getId()));assertFalse(queue.drainExecutable(System.currentTimeMillis()).stream().anyMatch(x->x.getId().equals(cmd.getId())));
        assertThrows(IllegalStateException.class,()->queue.recordGenericReceipt(cmd.getId(),claim.getGenericClaimId(),"{\"command_id\":\"SOURCE-other\"}"));
    }
    @Test public void falseCommitCannotBecomeSuccessFromMemoryAndFreshProcessRecoversOriginal()throws Exception {falseCommitRecovery(false);}
    @Test public void falseCommitAfterDiskWriteRecoversOriginalWithoutRepeatingDeletion()throws Exception {falseCommitRecovery(true);}
    void falseCommitRecovery(boolean persisted)throws Exception {
        enqueue(queue,"SOURCE-first");QueueRestoreRequest request=queue.reviewDiscard();store.failAt=store.commits+2;store.persistOnFailure=persisted;
        assertThrows(IllegalStateException.class,()->discard(queue,request));assertThrows(IllegalStateException.class,()->queue.restoreResult(request.getOperationId()));
        List<String> command=List.of(Path.of(System.getProperty("java.home"),"bin","java").toString(),"-cp",childClasspath(),getClass().getName(),"SOURCE-recover",store.file.toString(),request.getOperationId());
        Process child=new ProcessBuilder(command).redirectErrorStream(true).redirectOutput(directory.resolve("restart.log").toFile()).start();
        try {assertTrue(child.waitFor(20,TimeUnit.SECONDS));assertEquals(new String(Files.readAllBytes(directory.resolve("restart.log")),java.nio.charset.StandardCharsets.UTF_8),0,child.exitValue());assertTrue(new String(Files.readAllBytes(directory.resolve("restart.log")),java.nio.charset.StandardCharsets.UTF_8).contains("SOURCE original recovery APPLIED "+request.getOperationId()));}
        finally {if(child.isAlive()){child.destroyForcibly();assertTrue(child.waitFor(5,TimeUnit.SECONDS));}}
    }
    @Test public void explicitOwningPrivacyEraseRemainsWholeCanonicalStoreErase()throws Exception {
        enqueue(queue,"SOURCE-selected");QueueRestoreRequest request=queue.reviewDiscard();discard(queue,request);queue.upsert(legacy("session","SESSION_ENVELOPE",1));queue.clear();assertEquals("",store.memory.get("index"));assertFalse(store.memory.keySet().stream().anyMatch(k->k.startsWith("cmd_")||k.startsWith("restore_operation_")));
    }
    static String childClasspath()throws Exception {
        LinkedHashSet<String> paths=new LinkedHashSet<>();
        for(Class<?> c:List.of(QueueRestorationActualStoreTest.class,android.util.Base64.class,EncryptedCommandQueue.class))paths.add(Path.of(c.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        for(ClassLoader cl=QueueRestorationActualStoreTest.class.getClassLoader();cl!=null;cl=cl.getParent())if(cl instanceof java.net.URLClassLoader)for(var url:((java.net.URLClassLoader)cl).getURLs())if(url.getProtocol().equals("file"))paths.add(Path.of(url.toURI()).toString());
        paths.addAll(Arrays.asList(System.getProperty("java.class.path").split(File.pathSeparator)));return String.join(File.pathSeparator,paths);
    }
    public static void main(String[] args)throws Exception {
        if(args.length!=3||!args[0].equals("SOURCE-recover"))throw new IllegalArgumentException("SOURCE recovery arguments required");
        installFixtureProvider();Store store=new Store(Path.of(args[1]));var actor=new AtomicReference<>(owner("SOURCE-profile","SOURCE-auth"));EncryptedCommandQueue q=queue(store,actor);
        Method read=EncryptedCommandQueue.class.getDeclaredMethod("originalRestore",String.class);read.setAccessible(true);QueueRestoreRecord record=(QueueRestoreRecord)read.invoke(q,args[2]);
        QueueRestoreResult original=record.getResult();QueueRestoreResult result=original!=null?q.restoreResult(args[2]):discard(q,record.getRequest());assertEquals("APPLIED",result.getState());if(original!=null)assertEquals(original,result);
        assertTrue(result.getRemovedIds().stream().noneMatch(id->store.memory.containsKey("cmd_"+id)));System.out.println("SOURCE original recovery APPLIED "+args[2]);
    }
}
