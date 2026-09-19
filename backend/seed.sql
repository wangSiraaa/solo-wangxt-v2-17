-- 本地演示数据：脱敏样本、测试身份、初始授权
-- 注意：所有参与者均为虚构，记录为区间化/类别化的脱敏数据

-- ============ 参与者（化名 + 代号） ============
INSERT INTO participants (id, code, display_name) VALUES
  (1001, 'P-1001', '林安（化名）'),
  (1002, 'P-1002', '周禾（化名）'),
  (1003, 'P-1003', '沈越（化名）'),
  (1004, 'P-1004', '何知（化名）');

SELECT setval(pg_get_serial_sequence('participants','id'), 1004, true);

-- ============ 研究员 / 管理员 ============
INSERT INTO researchers (id, code, display_name, institution) VALUES
  (2001, 'R-2001', '顾研（演示账号）', '城市公共卫生学院'),
  (2002, 'R-2002', '许策（演示账号）', '区域慢病研究所');
SELECT setval(pg_get_serial_sequence('researchers','id'), 2002, true);

INSERT INTO admins (id, code, display_name) VALUES
  (3001, 'A-3001', '管理员（演示账号）');
SELECT setval(pg_get_serial_sequence('admins','id'), 3001, true);

-- ============ 测试身份 ============
INSERT INTO identities (identity_key, role, participant_id, researcher_id, admin_id, label) VALUES
  ('participant-1001','participant',1001,NULL,NULL,'参与者：林安 P-1001'),
  ('participant-1002','participant',1002,NULL,NULL,'参与者：周禾 P-1002'),
  ('participant-1003','participant',1003,NULL,NULL,'参与者：沈越 P-1003'),
  ('participant-1004','participant',1004,NULL,NULL,'参与者：何知 P-1004'),
  ('researcher-2001','researcher',NULL,2001,NULL,'研究员：顾研 R-2001（公卫学院）'),
  ('researcher-2002','researcher',NULL,2002,NULL,'研究员：许策 R-2002（慢病所）'),
  ('admin-3001','admin',NULL,NULL,3001,'数据管理员：A-3001');

-- ============ 用途 ============
INSERT INTO purposes (id, code, title, description) VALUES
  (1, 'diabetes_research', '糖尿病风险因素研究',
   '分析血糖、BMI 等区间指标与糖尿病筛查结果的关联，仅用于统计建模，不重新识别个人。'),
  (2, 'cardiovascular_research', '心血管风险预测研究',
   '基于血压区间、心率等脱敏指标评估心血管风险模型。');
SELECT setval(pg_get_serial_sequence('purposes','id'), 2, true);

-- ============ 脱敏样本数据集 ============
INSERT INTO datasets (id, code, title, description, is_deidentified) VALUES
  (1, 'ds-screening-2026', '2026 社区慢病筛查脱敏样本',
   '来自虚构社区筛查的区间化样本：无姓名、联系方式与精确日期，年龄按 5 岁分组，指标按区间记录。', TRUE);

-- 每人 2 行，共 8 行
INSERT INTO dataset_records (dataset_id, participant_id, row_no, payload) VALUES
  (1,1001,1,'{"age_band":"45-49","sex":"F","bmi_band":"28-30","hba1c_band":"6.5-6.9","screening":"positive","note":"区间值，已脱敏"}'),
  (1,1001,2,'{"age_band":"45-49","sex":"F","bmi_band":"27-29","hba1c_band":"6.1-6.4","screening":"negative","note":"区间值，已脱敏"}'),
  (1,1002,3,'{"age_band":"60-64","sex":"M","bmi_band":"24-26","hba1c_band":"7.0-7.4","screening":"positive","note":"区间值，已脱敏"}'),
  (1,1002,4,'{"age_band":"60-64","sex":"M","bmi_band":"25-27","hba1c_band":"6.5-6.9","screening":"positive","note":"区间值，已脱敏"}'),
  (1,1003,5,'{"age_band":"30-34","sex":"F","bmi_band":"21-23","hba1c_band":"5.5-5.9","screening":"negative","note":"区间值，已脱敏"}'),
  (1,1003,6,'{"age_band":"30-34","sex":"F","bmi_band":"22-24","hba1c_band":"5.6-6.0","screening":"negative","note":"区间值，已脱敏"}'),
  (1,1004,7,'{"age_band":"55-59","sex":"M","bmi_band":"30-32","hba1c_band":"6.2-6.6","screening":"negative","note":"区间值，已脱敏"}'),
  (1,1004,8,'{"age_band":"55-59","sex":"M","bmi_band":"29-31","hba1c_band":"6.8-7.2","screening":"positive","note":"区间值，已脱敏"}');

-- ============ 初始授权状态与版本历史 ============
-- 糖尿病研究：4 人全部授予（演示撤回的起点）
-- 心血管研究：仅 1001、1003 授予，1002 未授予、1004 已撤回（展示不同授权范围）
INSERT INTO consents (participant_id, purpose_id, version, status, granted_at) VALUES
  (1001,1,1,'granted', now() - interval '30 days'),
  (1002,1,1,'granted', now() - interval '30 days'),
  (1003,1,1,'granted', now() - interval '30 days'),
  (1004,1,1,'granted', now() - interval '30 days'),
  (1001,2,1,'granted', now() - interval '20 days'),
  (1003,2,1,'granted', now() - interval '20 days'),
  (1004,2,2,'withdrawn', now() - interval '10 days');

-- 1004 的心血管授权先授予后撤回（两个版本事件，体现版本化）
INSERT INTO consent_events (consent_id, version, action, reason, occurred_at)
SELECT id, 1, 'granted', '初始授权', now() - interval '20 days' FROM consents WHERE participant_id=1004 AND purpose_id=2;
INSERT INTO consent_events (consent_id, version, action, reason, occurred_at)
SELECT id, 2, 'withdrawn', '不再希望数据用于心血管研究', now() - interval '10 days' FROM consents WHERE participant_id=1004 AND purpose_id=2;
-- 其余授予者补一条 granted 事件
INSERT INTO consent_events (consent_id, version, action, reason, occurred_at)
SELECT id, 1, 'granted', '初始授权', granted_at FROM consents
WHERE (participant_id,purpose_id) IN ((1001,1),(1002,1),(1003,1),(1004,1),(1001,2),(1003,2));

-- 授权锁位：为所有 4×2 组合预置
INSERT INTO consent_slots (participant_id, purpose_id)
SELECT p.id, pu.id FROM participants p CROSS JOIN purposes pu;
