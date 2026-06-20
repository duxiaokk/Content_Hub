import { useState, useMemo } from 'react';
import { Image, Carousel, Space, Tag } from 'antd';
import { PictureOutlined, VideoCameraOutlined, LinkOutlined } from '@ant-design/icons';

export interface MediaData {
  cover_url?: string;
  video_url?: string;
  images?: string[];
  source_url?: string;
}

interface MediaGalleryProps {
  mediaJson?: string | null;
  maxImageHeight?: number;
}

export function parseMediaJson(raw?: string | null): MediaData | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === 'object' && parsed !== null) {
      return parsed as MediaData;
    }
  } catch {
    // ignore parse error
  }
  return null;
}

function isBilibiliUrl(url: string): boolean {
  return url.includes('bilibili.com') || url.includes('b23.tv');
}

function extractBvid(url: string): string | null {
  const match = url.match(/(?:bilibili\.com\/video\/|bv)([a-zA-Z0-9]+)/i);
  return match?.[1] ?? null;
}

function isVideoUrl(url: string): boolean {
  return /\.(mp4|mov|avi|mkv|webm)(\?.*)?$/i.test(url) || url.includes('video');
}

export default function MediaGallery({ mediaJson, maxImageHeight = 400 }: MediaGalleryProps) {
  const media = useMemo(() => parseMediaJson(mediaJson), [mediaJson]);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);

  if (!media) return null;

  const { cover_url, video_url, images = [], source_url } = media;

  // 收集所有可预览图片（封面 + 图片列表）
  const allImages = useMemo(() => {
    const list: string[] = [];
    if (cover_url) list.push(cover_url);
    images.forEach((img) => {
      if (!list.includes(img)) list.push(img);
    });
    return list;
  }, [cover_url, images]);

  return (
    <div style={{ marginBottom: 24 }}>
      {/* 封面图 / 视频区 */}
      {cover_url && !video_url && (
        <div
          style={{
            borderRadius: 12,
            overflow: 'hidden',
            marginBottom: 16,
            cursor: 'pointer',
          }}
          onClick={() => {
            setPreviewIndex(0);
            setPreviewVisible(true);
          }}
        >
          <img
            src={cover_url}
            alt="cover"
            style={{
              width: '100%',
              maxHeight: maxImageHeight,
              objectFit: 'cover',
              display: 'block',
            }}
            loading="lazy"
          />
        </div>
      )}

      {/* Bilibili 视频嵌入 */}
      {video_url && isBilibiliUrl(video_url) && (
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              position: 'relative',
              paddingBottom: '56.25%',
              height: 0,
              borderRadius: 12,
              overflow: 'hidden',
              background: '#000',
            }}
          >
            {(() => {
              const bvid = extractBvid(video_url);
              if (bvid) {
                return (
                  <iframe
                    src={`https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1`}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      border: 'none',
                    }}
                    allowFullScreen
                    title="bilibili video"
                  />
                );
              }
              // fallback: 普通视频标签
              return (
                <video
                  src={video_url}
                  controls
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                  }}
                />
              );
            })()}
          </div>
          {source_url && (
            <Space size={4} style={{ marginTop: 8 }}>
              <LinkOutlined style={{ color: '#999', fontSize: 12 }} />
              <a href={source_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: '#666' }}>
                查看原平台
              </a>
            </Space>
          )}
        </div>
      )}

      {/* 普通视频 */}
      {video_url && !isBilibiliUrl(video_url) && (
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              borderRadius: 12,
              overflow: 'hidden',
              background: '#000',
            }}
          >
            <video
              src={video_url}
              controls
              preload="metadata"
              style={{
                width: '100%',
                maxHeight: maxImageHeight,
                display: 'block',
              }}
            />
          </div>
          {source_url && (
            <Space size={4} style={{ marginTop: 8 }}>
              <LinkOutlined style={{ color: '#999', fontSize: 12 }} />
              <a href={source_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: '#666' }}>
                查看原平台
              </a>
            </Space>
          )}
        </div>
      )}

      {/* 图片画廊（无视频且有图片时） */}
      {!video_url && allImages.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <Space size={4} style={{ marginBottom: 8 }}>
            <PictureOutlined style={{ color: '#1677ff' }} />
            <span style={{ fontSize: 14, color: '#666', fontWeight: 500 }}>图片画廊</span>
            <Tag style={{ fontSize: 12, padding: '0 6px', lineHeight: '18px' }}>{allImages.length} 张</Tag>
          </Space>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
              gap: 8,
            }}
          >
            {allImages.map((url, idx) => (
              <div
                key={`${url}-${idx}`}
                style={{
                  borderRadius: 8,
                  overflow: 'hidden',
                  cursor: 'pointer',
                  aspectRatio: '4 / 3',
                }}
                onClick={() => {
                  setPreviewIndex(idx);
                  setPreviewVisible(true);
                }}
              >
                <img
                  src={url}
                  alt={`img-${idx}`}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    display: 'block',
                  }}
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 图片预览 */}
      <Image.PreviewGroup
        preview={{
          visible: previewVisible,
          current: previewIndex,
          onVisibleChange: (v) => setPreviewVisible(v),
        }}
      >
        {allImages.map((url, idx) => (
          <Image key={`${url}-${idx}`} src={url} style={{ display: 'none' }} />
        ))}
      </Image.PreviewGroup>
    </div>
  );
}

/**
 * 列表页卡片封面缩略图
 */
export function PostCardCover({ mediaJson }: { mediaJson?: string | null }) {
  const media = useMemo(() => parseMediaJson(mediaJson), [mediaJson]);
  const cover = media?.cover_url;
  const videoUrl = media?.video_url;

  if (!cover && !videoUrl) return null;

  return (
    <div
      style={{
        width: '100%',
        height: 160,
        borderRadius: '8px 8px 0 0',
        overflow: 'hidden',
        position: 'relative',
        background: '#f0f0f0',
      }}
    >
      {cover ? (
        <img
          src={cover}
          alt="cover"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
          }}
          loading="lazy"
        />
      ) : (
        <div
          style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#999',
          }}
        >
          <VideoCameraOutlined style={{ fontSize: 32 }} />
        </div>
      )}
      {videoUrl && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            background: 'rgba(0,0,0,0.6)',
            color: '#fff',
            borderRadius: 4,
            padding: '2px 8px',
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <VideoCameraOutlined />
          <span>视频</span>
        </div>
      )}
    </div>
  );
}
