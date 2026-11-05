"""Content-sized cards for the All tweets grid; other views keep their delegate."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QFontMetrics, QTextLayout, QTextOption, QPen
from PySide6.QtWidgets import QStyle
from library import source_tweet_url
from text_presentation import readable_text

ROLE = Qt.ItemDataRole.UserRole


def font(pixels, bold=False):
    value = QFont('Microsoft YaHei UI')
    value.setPixelSize(pixels)
    value.setBold(bold)
    return value


def lines(value, width, limit, text_font):
    """Measure and elide with the same font and line breaks used by the painter."""
    value = str(value or '').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\u2028')
    if not value:return [],False
    utf16=value.encode('utf-16-le')
    layout = QTextLayout(value, text_font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    result, end = [], 0
    for _ in range(limit):
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1, width))
        end = line.textStart()+line.textLength()
        result.append(utf16[line.textStart()*2:end*2].decode('utf-16-le').replace('\u2028', '').rstrip())
    layout.endLayout()
    clipped = end*2 < len(utf16)
    if clipped and result:
        result[-1] = QFontMetrics(text_font).elidedText(result[-1]+'…', Qt.TextElideMode.ElideRight, max(1,width))
    return result, clipped


def masonry_frames(heights, available, columns, gap=12):
    width = max(1, (available-gap*(columns-1))//columns)
    bottoms = [0]*columns
    frames = []
    for height in heights:
        column = min(range(columns), key=lambda i:bottoms[i])
        frames.append(QRect(column*(width+gap), bottoms[column], width, height))
        bottoms[column] += height+gap
    return frames, max(0,max(bottoms, default=gap)-gap)


class AdaptiveCards:
    def __init__(self, window, labels, colors, star):
        self.window, self.labels, self.colors, self.star = window, labels, colors, star
        self.body_font, self.small_font = font(14), font(12)

    def excerpt(self, doc):
        if doc.get('status') == 'pending':
            return '正文待补全 · 点击补充核对'
        return readable_text((doc.get('content') if self.window.language.currentIndex()==2 else
                doc.get('translation_zh') or doc.get('content')) or '',doc.get('post_type',''))

    def quote(self, doc):
        if doc.get('post_type') != 'quote':
            return ''
        if not source_tweet_url(doc) and not doc.get('quote_summary'):
            return ''
        source = self.window.card_sources.get((doc.get('account'),str(doc.get('source_tweet_id') or
                   (doc.get('metadata') or {}).get('quoted_id') or '')))
        if source:
            author = source.get('author') or source.get('handle') or '来源作者'
            return author+'：'+self.excerpt(source)
        return doc.get('quote_summary') if self.window.language.currentIndex()!=2 and doc.get('quote_summary') else '来源正文未在本地显示，可在右侧查看来源推文。'

    def plan(self, doc, width, dimensions=()):
        inner = max(1,width-36)
        y = 68
        credit = ''
        if doc.get('post_type')=='retweet':
            credit = (doc.get('account_name') or doc.get('account_handle') or '归档账号')+' 转推了 '+(doc.get('author') or doc.get('handle') or '来源作者')
        credit_rect = QRect(18,y,inner,20) if credit else QRect()
        if credit:y += 25
        has_media = bool(doc.get('images') or doc.get('videos'))
        body, clipped = lines(self.excerpt(doc) or ('' if has_media else '无文字正文'),inner,4 if has_media else 6,self.body_font)
        body_rect = QRect(18,y,inner,len(body)*23)
        if body:y += body_rect.height()+10
        media = QRect()
        cells = []
        if has_media:
            count = min(4,len(doc.get('images',[]))) or 1
            if count == 1:
                w,h = dimensions[0] if dimensions else (16,9)
                height = min(240,max(96,round(inner*h/max(1,w))))
            elif count==2:
                height = min(240,max(140,round(inner*.60)))
            else:
                height = min(260,max(160,round(inner*.85)))
            media = QRect(18,y,inner,height)
            if count==1:
                cells=[QRect(media)]
            else:
                cell_width=(inner-5)//2
                if count==2:
                    cells=[QRect(18+i*(cell_width+5),y,cell_width,height) for i in range(2)]
                elif count==3:
                    cells=[QRect(18,y,cell_width,height),QRect(18+cell_width+5,y,cell_width,(height-5)//2),
                           QRect(18+cell_width+5,y+(height+5)//2,cell_width,(height-5)//2)]
                else:
                    cells=[QRect(18+(i%2)*(cell_width+5),y+(i//2)*((height+5)//2),cell_width,(height-5)//2) for i in range(4)]
            y += height+12
        quote_value=self.quote(doc)
        quote_lines,_=lines(quote_value,max(1,inner-22),2,self.small_font)
        quote_rect=QRect(18,y,inner,36+len(quote_lines)*20) if quote_value else QRect()
        if quote_value:y += quote_rect.height()+12
        footer=QRect(18,y,inner,19)
        return dict(height=y+35, body=body_rect, body_lines=body, clipped=clipped,
                    media=media,cells=cells,quote=quote_rect,quote_lines=quote_lines,
                    quote_link=QRect(26,quote_rect.top()+7,inner-16,18) if quote_value else QRect(),
                    credit=credit,credit_rect=credit_rect,footer=footer)

    @staticmethod
    def draw_lines(painter, rect, values, text_font, color, step):
        painter.setFont(text_font)
        painter.setPen(QColor(color))
        painter.save()
        painter.setClipRect(rect)
        ascent=QFontMetrics(text_font).ascent()
        for i,value in enumerate(values):
            painter.drawText(rect.left(),rect.top()+ascent+i*step,value)
        painter.restore()

    def paint(self,painter,option,index):
        doc=index.data(ROLE) or {}
        plan=self.plan(doc,option.rect.width(),index.data(ROLE+5) or ())
        painter.save()
        painter.translate(option.rect.topLeft())
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setPen(QPen(QColor('#79dfc2' if selected else '#41566d' if hovered else '#2d3c50'),1.3 if selected else 1))
        painter.setBrush(QColor('#1c2e35' if selected else '#1e2b3b' if hovered else '#192330'))
        painter.drawRoundedRect(QRect(3,3,option.rect.width()-6,option.rect.height()-6),11,11)
        author=doc.get('author') or doc.get('handle') or '未知作者'
        kind=doc.get('post_type','original') if doc.get('status')=='archived' else None
        badge=self.labels.get(kind,'待核对')
        painter.setFont(self.small_font)
        badge_width=QFontMetrics(self.small_font).horizontalAdvance(badge)+14
        badge_rect=QRect(option.rect.width()-18-badge_width,17,badge_width,23)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#293b4d'))
        painter.drawRoundedRect(badge_rect,4,4)
        painter.setPen(QColor(self.colors.get(kind,'#b4bfcd')))
        painter.drawText(badge_rect,Qt.AlignmentFlag.AlignCenter,badge)
        avatar=QRect(18,18,32,32)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#2c424e'));painter.drawEllipse(avatar)
        painter.setFont(font(15));painter.setPen(QColor('#9ce8d5'));painter.drawText(avatar,Qt.AlignmentFlag.AlignCenter,author[0])
        author_rect=QRect(60,16,max(1,badge_rect.left()-70),23)
        if doc.get('favorite'):
            star=QRect(author_rect.right()-18,18,17,17)
            painter.setPen(QPen(QColor('#ffe08a'),1));painter.setBrush(QColor('#ffd35e'));painter.drawPolygon(self.star(star))
            author_rect.adjust(0,0,-24,0)
        painter.setFont(font(14,True));painter.setPen(QColor('#e8f0f9'))
        painter.drawText(author_rect,Qt.AlignmentFlag.AlignVCenter,QFontMetrics(painter.font()).elidedText(author,Qt.TextElideMode.ElideRight,max(1,author_rect.width())))
        painter.setFont(self.small_font);painter.setPen(QColor('#9eafc5'))
        date=(doc.get('date_beijing') or '').replace('T',' ')[:16]
        painter.drawText(QRect(60,40,option.rect.width()-78,18),Qt.AlignmentFlag.AlignVCenter,date)
        if plan['credit']:
            self.draw_lines(painter,plan['credit_rect'],[QFontMetrics(self.small_font).elidedText('↻ '+plan['credit'],Qt.TextElideMode.ElideRight,plan['credit_rect'].width())],self.small_font,'#acbcd0',20)
        self.draw_lines(painter,plan['body'],plan['body_lines'],self.body_font,'#e1eaf6',23)
        if not plan['media'].isNull():
            pixmaps=index.data(ROLE+3) or {}
            paths=index.data(ROLE+4) or []
            for i,cell in enumerate(plan['cells']):
                painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#0d151e'));painter.drawRoundedRect(cell,5,5)
                pixmap=pixmaps.get(paths[i]) if i<len(paths) else index.data(ROLE+1) if i==0 else None
                if pixmap and not pixmap.isNull():
                    fitted=pixmap.scaled(cell.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                    painter.drawPixmap(cell.center().x()-fitted.width()//2,cell.center().y()-fitted.height()//2,fitted)
                else:
                    painter.setFont(self.small_font);painter.setPen(QColor('#92a8bf'))
                    painter.drawText(cell,Qt.AlignmentFlag.AlignCenter,'视频封面待生成' if doc.get('videos') and not doc.get('images') else '缩略图加载中')
            count=len(doc.get('images',[]))
            if count>1 or doc.get('videos'):
                if doc.get('videos') and not doc.get('images'):
                    seconds=int(index.data(ROLE+2) or 0)//1000
                    text=f'▷ {seconds//60:02}:{seconds%60:02}' if seconds else '▷ 视频'
                else:text=f'{count} 张图片'+(f" · {len(doc['videos'])} 视频" if doc.get('videos') else '')
                painter.setFont(self.small_font)
                width=QFontMetrics(self.small_font).horizontalAdvance(text)+14
                rect=QRect(plan['media'].right()-width-5,plan['media'].bottom()-28,width,23)
                painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(12,22,31,230));painter.drawRoundedRect(rect,4,4)
                painter.setPen(QColor('#e1f4f1'));painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,text)
        if not plan['quote'].isNull():
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#14202c'));painter.drawRoundedRect(plan['quote'],5,5)
            painter.fillRect(QRect(plan['quote'].left(),plan['quote'].top()+5,2,plan['quote'].height()-10),QColor('#7f9abc'))
            painter.setFont(self.small_font);painter.setPen(QColor('#b4cff4'))
            painter.drawText(plan['quote_link'],Qt.AlignmentFlag.AlignVCenter,'引用来源 ↗' if source_tweet_url(doc) else '引用来源')
            body=plan['quote'].adjusted(10,31,-10,-5)
            self.draw_lines(painter,body,plan['quote_lines'],self.small_font,'#b5c4d8',20)
        painter.setFont(self.small_font);painter.setPen(QColor('#9eafc5'))
        if doc.get('images') or doc.get('videos'):media='图片' if doc.get('images') else '视频'
        else:media='纯文字' if doc.get('media_state')=='text' else '媒体信息待核对' if doc.get('media_state')=='unknown' else '媒体待下载 / 缺失'
        suffix='查看全文' if plan['clipped'] else '原文' if self.window.language.currentIndex()==2 else '中文译文' if doc.get('translation_zh') else '待翻译' if doc.get('content') else ''
        painter.drawText(plan['footer'],Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,media)
        painter.drawText(plan['footer'],Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,suffix)
        painter.restore()
