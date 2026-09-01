# EvStereo3D comparator artifact 索要邮件（草稿，2026-08-31，红队 §3 行动项 2）

**目的**：闭合 comparator identity（论文 19.62/12.93 vs 公开 checkpoint 8.0215/3.6448）。
**纪律**：邮件发出时间戳本身是 rebuttal 证据；语气是复现协作，不是质疑。
**发件人**：用户本人（学术邮箱）。**抄送建议**：无。**附件**：无（首封不带）。

---

Subject: Reproducing Ev-Stereo3D on DSEC-3DOD — request for training artifacts

Dear Jae-Young Kang, Hoonhee Cho, and Prof. Yoon,

We are working on stereo event-based 3D detection on DSEC-3DOD and are using
Ev-Stereo3D (ICCV 2025) as our primary baseline. Thank you for releasing the
code and checkpoint — the repository has been very helpful.

To make sure our comparison to your paper numbers is fair, we have been trying
to reproduce the reported results (Vehicle/Pedestrian moderate 19.62/12.93)
from the public artifacts, and we are currently unable to close the gap with
the released checkpoint alone. Concretely, on our side:

1. The released checkpoint metadata reads epoch 22 / iteration 46,200, while
   the supplementary material describes 60 training epochs. Could you share
   the 60-epoch checkpoint used for the paper tables, or confirm which
   checkpoint produced them?
2. The public checkpoint loads 353/388 tensors against the released config;
   the 35 missing tensors are all under `dense_head_2d.*`. Is there a config
   or code revision that matches the paper checkpoint exactly?
3. The paper describes 10 ms event slices, while the released preprocessing
   extracts 50 ms windows split into ten nominal chunks, and the YAML
   references a voxel path that is not part of the release. Could you share
   the exact preprocessing (or one canonical voxel file) used for the paper?
4. If possible, the validation prediction files (pickle/txt) behind Table 1
   would let us verify evaluator parity directly — we are happy to share our
   evaluator-parity harness in return (we have verified bit-exact agreement
   with your evaluator on identical predictions).

We will of course cite and report your published numbers as stated in the
paper; these artifacts would only be used to make the comparison protocol
airtight. Happy to share our findings either way.

Best regards,
[姓名 / 单位 / 邮箱]

---

**登记**：发出后把发送时间与回复情况记入 identity dossier
（supplementary 一页纸），并在台账 §14 comparator 条目下追加一行。
