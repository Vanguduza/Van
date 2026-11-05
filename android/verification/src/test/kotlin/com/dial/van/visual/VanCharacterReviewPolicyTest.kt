package com.dial.van.visual

import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import kotlin.test.assertEquals

class VanCharacterReviewPolicyTest {
    private val binary=ByteArray(2_048){(it%251).toByte()}
    private fun sha(v:ByteArray)=MessageDigest.getInstance("SHA-256").digest(v).joinToString(""){"%02x".format(it)}
    private val request="b".repeat(64)
    private val commit="c".repeat(40)
    private fun context()=JSONObject().apply {
        put("schema","van.character.context/1");put("asset_sha256",sha(binary))
        put("gestures",JSONArray().apply {VanContextGesture.entries.forEach {g->put(JSONObject().apply{
            put("code",g.code);put("name",g.name);put("duration_ms",g.durationMs);put("legacy_action",g.legacyAction.code)
        })}})
    }.toString().toByteArray()
    private fun marker(context:ByteArray)=JSONObject().apply {
        put("schema","van.character-review.package/1");put("review_only",true);put("production_accepted",false);put("physical_accepted",false)
        put("admission_state","UNACCEPTED_CANDIDATE");put("application_id",VanCharacterReviewPolicy.APPLICATION_ID)
        put("build_type","characterReview");put("source_commit",commit);put("request_sha256",request)
        put("rive_sha256",sha(binary));put("context_sha256",sha(context));put("rive_runtime","9.13.10")
    }
    private fun validate(data:ByteArray=binary,ctx:ByteArray=context(),raw:String=marker(ctx).toString(),
        debug:Boolean=true,enabled:Boolean=true,kind:String="characterReview",id:String=VanCharacterReviewPolicy.APPLICATION_ID)=
        VanCharacterReviewPolicy.validate(data,ctx,raw,debug,enabled,kind,id,request,sha(binary),sha(context()),commit)

    @Test fun exactReviewBuildCanSelectExactUnacceptedBundle(){assertTrue(validate())}
    @Test fun releaseBuildCannotActivateEvenWithMatchingFiles(){assertFalse(validate(debug=false,kind="release"))}
    @Test fun ordinaryDebugCannotActivateReviewByPresenceAlone(){assertFalse(validate(kind="debug",enabled=false))}
    @Test fun wrongApplicationCannotBorrowTheReviewAsset(){assertFalse(validate(id="com.dial.van"))}
    @Test fun noBuildFlagAloneIsSufficient(){for(d in listOf(false,true))for(r in listOf(false,true))for(t in listOf("debug","release","characterReview"))for(a in listOf("com.dial.van",VanCharacterReviewPolicy.APPLICATION_ID)){
        assertEquals(d&&r&&t=="characterReview"&&a==VanCharacterReviewPolicy.APPLICATION_ID,VanCharacterReviewPolicy.enabled(d,r,t,a))
    }}
    @Test fun changedBinaryRejectsMetadataEvenIfItsLengthLooksPlausible(){val b=binary.copyOf();b[10]=77;assertFalse(validate(data=b))}
    @Test fun changedContextByteRejectsEvenSemanticallyEquivalentJson(){assertFalse(validate(ctx=context()+byteArrayOf(32)))}
    @Test fun missingMalformedOrOversizeMarkerRejects(){for(s in listOf("","{}","[]","x".repeat(16_385)))assertFalse(validate(raw=s))}
    @Test fun acceptanceClaimCannotBeForgedInsideTheReviewMarker(){val c=context();for(k in listOf("production_accepted","physical_accepted")){val m=marker(c).put(k,true);assertFalse(validate(ctx=c,raw=m.toString()))}}
    @Test fun stringBooleansCannotBecomeAnAcceptanceOrReviewFlag(){val c=context();for(k in listOf("production_accepted","physical_accepted","review_only")){val m=marker(c).put(k,"false");assertFalse(validate(ctx=c,raw=m.toString()))}}
    @Test fun changedBuildSourceOrScopeInvalidatesMarker(){val c=context();for(k in listOf("source_commit","request_sha256","admission_state","rive_runtime","application_id","build_type")){val m=marker(c).put(k,"wrong");assertFalse(validate(ctx=c,raw=m.toString()))}}
    @Test fun missingFullContextExtensionCannotPretend26Actions(){val c=JSONObject(context().toString(Charsets.UTF_8)).apply{getJSONArray("gestures").remove(0)}.toString().toByteArray();assertFalse(validate(ctx=c,raw=marker(c).toString()))}
    @Test fun truncatedOrHugeAssetsAreRejectedBeforeNativeLoad(){assertFalse(validate(data=byteArrayOf(1)));assertFalse(validate(ctx=ByteArray(16_385)))}
    @Test fun reviewFilesAreDistinctFromAcceptedAndOldCandidatePaths(){assertEquals("van_review.riv",VanCharacterReviewPolicy.RIVE_FILE);assertEquals("van_review.context.json",VanCharacterReviewPolicy.CONTEXT_FILE);assertEquals("van-character-review.json",VanCharacterReviewPolicy.MARKER_FILE)}
}
