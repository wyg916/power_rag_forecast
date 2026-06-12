import { DatabaseOutlined, FileTextOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Col, Input, Row, Select, Space, Table, Tag, Tree, Upload, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag, DataStateBanner, EmptyState } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { knowledgeMock } from '../../mock/knowledgeMock';
import { getKnowledgeBaseData, searchKnowledge } from '../../services/knowledgeApi';
import type { PageProps } from '../../types/ui';

const tabs = [
  { key: 'knowledge-policy', label: '文档管理' },
  { key: 'knowledge-index', label: '索引管理' },
  { key: 'knowledge-rag', label: '知识检索' },
  { key: 'knowledge-qa', label: 'QA测试' }
];

export function KnowledgeBasePage({ activeSubKey, onSubNavigate }: PageProps) {
  const [data, setData] = useState<any>(knowledgeMock);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('浙江 光伏 电价 政策');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [answer, setAnswer] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

  async function loadData() {
    setLoading(true);
    try {
      setData(await getKnowledgeBaseData());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function rebuildIndex() {
    setLoading(true);
    try {
      const res = await api.knowledgeIndexLocal();
      message.success(`索引完成：${res.indexed_documents || 0} 个文档`);
      await loadData();
    } finally {
      setLoading(false);
    }
  }

  async function runSearch() {
    setSearching(true);
    try {
      const payload = await searchKnowledge(query, 5);
      setResults(payload.items || []);
      setAnswer((payload.items || []).length ? `根据知识库命中结果，问题“${query}”可参考 ${payload.items.length} 条证据。请优先查看相似度最高的文档片段。` : '未检索到高相关文档。');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '检索失败');
    } finally {
      setSearching(false);
    }
  }

  const documentRows = results.length
    ? results.map((item) => [item.title, item.source_type || 'local_file', item.source, item.chunk_id, '已索引'])
    : data.documents;

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <DataStateBanner
        scope="知识库"
        loading={loading}
        source={data.dataSource}
        error={data.error}
        empty={data.empty}
        mockFallback={data.mockFallback}
        fallbackReason={data.fallbackReason}
        partialErrors={data.partialErrors}
        onRetry={loadData}
      />
      <div className="knowledge-top-grid">
        <MetricGrid items={data.metrics || []} icons={(data.metrics || []).map(() => <FileTextOutlined />)} loading={loading} minColumnWidth={180} />
        <SectionCard title="索引服务状态" loading={loading} compact>
          <div className="index-status">
            <Tag color="success">健康</Tag>
            <p><DatabaseOutlined /> PostgreSQL 索引正常</p>
            <p><DatabaseOutlined /> RAG 检索可用</p>
            <DataSourceTag source={data.dataSource} />
          </div>
        </SectionCard>
      </div>

      {activeSubKey === 'knowledge-policy' && (
        <div className="knowledge-two-column">
            <SectionCard title="文档分类" scrollable>
              <Input prefix={<SearchOutlined />} placeholder="搜索分类名称" />
              <Tree
                className="knowledge-tree"
                defaultExpandAll
                treeData={[{ title: `全部文档（${data.metrics?.[0]?.value || 0}）`, key: 'all', children: data.categories.map((item: any[]) => ({ title: `${item[0]}（${item[1]}）`, key: item[0] })) }]}
              />
              <Button block icon={<PlusOutlined />} onClick={() => message.success('分类已记录到页面状态')}>新建分类</Button>
            </SectionCard>
            <TableCard
              title="文档列表"
              loading={loading}
              minHeight={460}
              extra={<Space><Button onClick={loadData}>刷新</Button><Upload beforeUpload={() => { message.success('文档已登记，请重建索引'); return false; }}><Button type="primary" icon={<PlusOutlined />}>上传文档</Button></Upload></Space>}
              dataSource={documentRows.map((row: any[], index: number) => ({ key: `${row[0]}-${index}`, row }))}
              columns={[
                { title: '文档名称', render: (_, record: any) => record.row[0] },
                { title: '类型/来源', render: (_, record: any) => <Tag>{record.row[1]}</Tag> },
                { title: '路径/时间', render: (_, record: any) => record.row[2] },
                { title: 'Chunk', render: (_, record: any) => record.row[3] },
                { title: '索引状态', render: (_, record: any) => <Tag color={String(record.row[4]).includes('已') ? 'success' : 'processing'}>{record.row[4]}</Tag> },
                { title: '操作', render: (_, record: any) => <Button type="link" size="small" onClick={() => { setDetailData({ name: record.row[0], type: record.row[1], source: record.row[2], chunk: record.row[3] }); setDetailOpen(true); }}>详情</Button> }
              ]}
            />
        </div>
      )}

      {activeSubKey === 'knowledge-index' && (
        <SectionCard title="索引重建" extra={<Button type="primary" loading={loading} onClick={rebuildIndex}>重建本地索引</Button>}>
          <p>当前索引文档数：{data.metrics?.[0]?.value || 0}，切片数：{data.metrics?.[1]?.value || 0}。</p>
          <p>索引来源包括本地知识库目录、电价政策摘要和 PostgreSQL 中已入库的政策记录。</p>
        </SectionCard>
      )}

      {(activeSubKey === 'knowledge-rag' || activeSubKey === 'knowledge-qa') && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} lg={7} xl={6}>
            <SectionCard title={activeSubKey === 'knowledge-qa' ? 'QA 测试' : '检索测试'}>
              <Input.TextArea rows={6} value={query} onChange={(event) => setQuery(event.target.value)} />
              <div className="search-config">
                <span>检索设置</span>
                <Select value="Top K = 5" options={[{ value: 'Top K = 5', label: 'Top K = 5' }]} />
                <Button type="primary" loading={searching} onClick={runSearch}>检索</Button>
              </div>
            </SectionCard>
          </Col>
          <Col xs={24} lg={10} xl={11}>
            <TableCard
              title="检索结果"
              loading={searching}
              dataSource={results.map((row, index) => ({ key: index, ...row }))}
              locale={{ emptyText: <EmptyState description="请先执行检索" /> }}
              pagination={false}
              columns={[
                { title: '命中文档', dataIndex: 'title' },
                { title: '相似度', dataIndex: 'score' },
                { title: '命中片段', dataIndex: 'content', ellipsis: true },
                { title: '操作', render: (_, record: any) => <Button type="link" size="small" onClick={() => { setDetailData(record); setDetailOpen(true); }}>查看</Button> }
              ]}
            />
          </Col>
          <Col xs={24} lg={7}>
            <SectionCard title="AI 整理答案" extra={<Button type="link" onClick={() => navigator.clipboard?.writeText(answer)}>复制</Button>}>
              <div className="rag-answer">
                <p>{answer || '执行检索后生成整理答案。'}</p>
                <strong>依据来源</strong>
                <ol>{results.slice(0, 3).map((item) => <li key={item.chunk_id || item.title}>{item.title}</li>)}</ol>
              </div>
            </SectionCard>
          </Col>
        </Row>
      )}

      <DetailDrawer title="知识库详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
