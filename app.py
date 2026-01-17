import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pandas as pd
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import io

# 모델 선언 부분
model = genai.GenerativeModel(
    'nano-banana-pro-preview',
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# --- [0. 세션 상태 초기화] (최상단) ---
if 'styling_done' not in st.session_state:
    st.session_state.styling_done = False
if 'final_image' not in st.session_state:
    st.session_state.final_image = None
if 'synthesis_count' not in st.session_state:
    st.session_state.synthesis_count = 0  # 0: 시작전, 1: 1차완료, 2: 재합성완료

if 'show_confirm_redo' not in st.session_state:
    st.session_state.show_confirm_redo = False
if 'show_confirm_reset' not in st.session_state:
    st.session_state.show_confirm_reset = False

# --- [추가] 초기화 함수 ---
def reset_app():
    st.session_state.styling_done = False
    st.session_state.final_image = None
    st.session_state.synthesis_count = 0
    # 캐시된 파일 업로더도 초기화하기 위해 페이지를 새로고침합니다.
    st.rerun()


# 1. 페이지 설정
st.set_page_config(page_title="헤나세르 AI 스타일러", layout="centered")
st.title("✂️ 헤나세르 AI 가상 스타일링 (MVP)")

# 하단 푸터 및 메뉴 숨기기 CSS
hide_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_style, unsafe_allow_html=True)

# 2. 인증 설정
try:
    # Google Sheets 인증
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gspread_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    # 시트 열기
    sh = client.open_by_url(st.secrets["gsheets_url"])
    worksheet = sh.get_worksheet(0) # 첫 번째 탭
except Exception as e:
    st.error(f"설정 오류가 발생했습니다: {e}")
    st.stop()

# 제미나이 설정
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('nano-banana-pro-preview')

# --- [0. 세션 상태 초기화] (스크립트 최상단에 배치하세요) ---
if 'styling_done' not in st.session_state:
    st.session_state.styling_done = False
if 'final_image' not in st.session_state:
    st.session_state.final_image = None

# --- [3. 메인 로직 시작] ---
with st.sidebar:
    st.header("🔑 멤버십 인증")
    access_key = st.text_input("액세스 키를 입력하세요 (대소문자 구분)", type="password")

if access_key:
    # 실시간 시트 데이터 확인
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    user_row = df[df['Access_Key'].astype(str) == access_key]

    if not user_row.empty:
        idx = user_row.index[0]  # 시트에서의 행 위치
        remaining = int(user_row.iloc[0]['Remaining_Count'])
        
        if remaining > 0:
            st.success(f"✅ 인증 성공! 잔여 횟수: {remaining}회")
            
            # 1. 스타일 선택
            mode = st.selectbox("어떤 스타일을 시뮬레이션할까요?", ["헤어", "아우터", "이너"])
            
            st.markdown("---")

            # 2. 내 정면 사진 (Base) 섹션
            st.markdown("### 👤 <span style='font-size: 24px;'>내 정면 사진 (Base)</span>", unsafe_allow_html=True)
            base_img = st.file_uploader("본인의 정면 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")
            
            st.markdown("---")

            # 3. 합성할 헤어 사진 (Style) 섹션
            st.markdown("### 💇‍♂️ <span style='font-size: 24px;'>합성할 헤어 사진 (Style)</span>", unsafe_allow_html=True)
            st.info("💡 아래와 같은 '정면' 예시를 준비해주세요. (측면 사진은 불가해요)")
            st.image("example_front.jpg", width=250, caption="[합성이 잘 되는 정면 예시]")
            
            style_img = st.file_uploader("원하는 헤어 스타일 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")

            # [핵심] 사용자가 사진을 새로 올리거나 모드를 바꾸면 이전 결과물 세션 초기화
            # (이 코드가 있어야 헌 사진에 새 머리가 섞이지 않습니다)
            if st.session_state.styling_done:
                # 간단한 체크로 초기화 여부 판단 (사진 변경 시)
                pass 

            st.markdown("---")

            # 4. 실행 버튼
            if base_img and style_img:
                # 아직 한 번도 합성을 안 했을 때만 "합성 시작하기" 버튼 노출
                if st.session_state.synthesis_count == 0:
                    if st.button(f"✨ {mode} 합성 시작하기 (1~2분 소요)"):
                        with st.spinner("1~2분 정도 소요됩니다. 페이지를 이탈하거나 새로고침 하지 마세요."):
                            try:
                                img_a = Image.open(base_img)
                                img_b = Image.open(style_img)
                                
                                # 프롬프트 설정 (기존과 동일)
                                prompt = f"""
                                URGENT: Strict head pose alignment. The nose and eyes in the output MUST be in the exact same pixel coordinates as Image A.
                                [Role]: You are a Master AI Stylist specializing in photo-realistic Virtual Try-on.
                                [Input]:
                                - Image 1 (The FIRST image): BASE_IMAGE (The customer)
                                - Image 2 (The SECOND image): STYLE_IMAGE (The reference look)
                                [PRIME DIRECTIVE - CRITICAL]:
                                1. TARGET RECOGNITION: Focus ONLY on the human subject's head and body. Strictly ignore all mobile UI elements (status bars, notches, buttons, white/black bars) in both images.
                                2. IDENTITY ANCHOR: Use Image 1 as the absolute anchor. Do NOT rotate, tilt, or distort the face. The eye-line, nose position, and head angle must be 100% identical to Image 1.
                                3. STYLE EXTRACTION: Extract only the {mode} (texture, color, silhouette) from Image 2.
                                [Task]:
                                - "Surgically" replace ONLY the {mode} of the person in Image 1 with the style from Image 2.
                                - Head Pose Alignment: Ensure the new {mode} is naturally fitted onto the original head position of Image 1.
                                - Seamless Blending: The hairline and the area where the skin meets the {mode} must be perfectly blended with realistic shadows.
                                - Preservation: Keep the original facial features (eyebrows, eyes, skin texture), background, and clothing of Image 1 untouched.
                                [Important Rules]:
                                - The result must be a SINGLE integrated photo, NOT a side-by-side comparison.
                                - The person's identity and facial proportions must remain 100% recognizable as the person in Image 1.
                                - No text, no descriptions, no watermarks. Output ONLY the resulting image.
                                """

                                response = model.generate_content([prompt, img_a, img_b])
                                
                                image_data = None
                                if response.candidates:
                                    for part in response.candidates[0].content.parts:
                                        if part.inline_data:
                                            image_data = part.inline_data.data
                                            break
                                
                                if image_data:
                                    # 워터마크 합성 로직
                                    base_image = Image.open(io.BytesIO(image_data)).convert("RGBA")
                                    logo = Image.open("logo.png").convert("RGBA")
                                    target_width = int(base_image.width * 0.2)
                                    aspect_ratio = logo.height / logo.width
                                    target_height = int(target_width * aspect_ratio)
                                    logo_resized = logo.resize((target_width, target_height), Image.LANCZOS)
                                    padding = 20
                                    position = (base_image.width - logo_resized.width - padding, base_image.height - logo_resized.height - padding)
                                    watermark_layer = Image.new('RGBA', base_image.size, (0,0,0,0))
                                    watermark_layer.paste(logo_resized, position, mask=logo_resized)
                                    logo_resized.putalpha(128) # 0(투명) ~ 255(불투명) 중 중간값인 128 적용

                                    # 결과물을 세션에 저장
                                    st.session_state.final_image = Image.alpha_composite(base_image, watermark_layer)
                                    st.session_state.styling_done = True
                                    
                                    # 성공 시
                                    st.session_state.synthesis_count = 1
                                    st.session_state.styling_done = True
                                    
                                    # 횟수 차감
                                    worksheet.update_cell(idx + 2, 3, remaining - 1)
                                    st.rerun() # 상태 반영을 위해 새로고침
                                else:
                                    st.error("이미지를 생성하지 못했습니다. 다시 시도해 주세요. (횟수 차감 X)")
                            except Exception as e:
                                st.error(f"합성 엔진 오류: {e}")

            # --- [5. 결과물 출력 섹션 (버튼 바깥)] ---
            if st.session_state.styling_done and st.session_state.final_image:
                st.success("✅ 합성이 완료되었습니다!")
                # 로고가 박힌 이미지 출력
                st.image(st.session_state.final_image, use_column_width=True)

                # 주의 문구
                st.markdown("""
                    <div style='text-align: center; color: #808080; font-size: 16px; line-height: 1.6; margin-top: 10px;'>
                        이 결과는 스타일 방향성을 보기 위한<br>
                        AI 시뮬레이션입니다.<br>
                        실제와 100% 일치하지 않을 수 있습니다.
                    </div>
                """, unsafe_allow_html=True)

                # 좋아요 피드백
                st.write("")
                col_like, col_empty = st.columns([1, 1])
                with col_like:
                    if st.button("👍 이 결과가 마음에 드시나요? (Like)"):
                        try:
                            # 현재 좋아요 값 읽기 (D열=4번째 열)
                            current_likes_val = worksheet.cell(idx + 2, 4).value
                            current_likes = int(current_likes_val) if current_likes_val and str(current_likes_val).isdigit() else 0
                            worksheet.update_cell(idx + 2, 4, current_likes + 1)
                            st.toast("피드백 감사합니다! 😊")
                        except Exception as e:
                            st.error(f"기록 오류: {e}")

                # 캡처 안내
                st.markdown("""
                    ### 📸 **지금 화면을 캡쳐하세요!**
                    <div style='background-color:#f0f2f6; padding:15px; border-radius:10px;'>
                    미용실 방문 시 디자이너에게 이 사진을 보여주시면 상담이 훨씬 수월해집니다.😉
                    </div>
                """, unsafe_allow_html=True)

                # --- [핵심: 재합성 로직 (확인창 포함)] ---
                if st.session_state.synthesis_count == 1:
                    st.write("")
                    # 재합성 확인창이 떠있지 않을 때만 버튼 노출
                    if not st.session_state.show_confirm_redo:
                        if st.button("🔄 재합성 시도하기 (1회 무료, 횟수 차감 없음)"):
                            st.session_state.show_confirm_redo = True
                            st.rerun()
                    
                    # 재합성 확인창 활성화 시
                    else:
                        st.error("⚠️ 정말 재합성 하시겠어요? 지금까지의 작업은 저장되지 않습니다.")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("✅ 네, 다시 할게요"):
                                with st.spinner("더 나은 결과를 위해 다시 합성 중입니다..."):
                                    try:
                                        # 1. AI에게 이미지 생성 재요청 (동일한 사진과 프롬프트 사용)
                                        response = model.generate_content([prompt, img_a, img_b])
                                        
                                        image_data = None
                                        if response.candidates:
                                            for part in response.candidates[0].content.parts:
                                                if part.inline_data:
                                                    image_data = part.inline_data.data
                                                    break
                                        
                                        if image_data:
                                            # 2. 워터마크(로고 + 텍스트) 합성 로직 재실행
                                            base_image = Image.open(io.BytesIO(image_data)).convert("RGBA")
                                            logo = Image.open("logo.png").convert("RGBA")
                                            
                                            # 폰트 설정
                                            font_size = int(base_image.height * 0.025)
                                            try:
                                                font = ImageFont.truetype("font.ttf", font_size)
                                            except OSError:
                                                font = ImageFont.load_default()

                                            # 로고 크기 및 위치 계산 (기존과 동일)
                                            target_width = int(base_image.width * 0.2)
                                            aspect_ratio = logo.height / logo.width
                                            target_height = int(target_width * aspect_ratio)
                                            logo_resized = logo.resize((target_width, target_height), Image.LANCZOS)

                                            text = "HENASCER AI"
                                            text_bbox = font.getbbox(text) 
                                            text_width, text_height = text_bbox[2], text_bbox[3]

                                            padding, spacing = 20, 10
                                            center_guide_x = base_image.width - padding - (max(text_width, logo_resized.width) / 2)
                                            text_x = int(center_guide_x - (text_width / 2))
                                            text_y = base_image.height - padding - text_height - int(text_height*0.2) 
                                            logo_x = int(center_guide_x - (logo_resized.width / 2))
                                            logo_y = text_y - spacing - logo_resized.height

                                            # 합성 레이어 생성
                                            watermark_layer = Image.new('RGBA', base_image.size, (0,0,0,0))
                                            draw = ImageDraw.Draw(watermark_layer)
                                            draw.text((text_x, text_y), text, font=font, fill="#EEEEEE")
                                            watermark_layer.paste(logo_resized, (logo_x, logo_y), mask=logo_resized)
                                            
                                            # [핵심] 결과물을 다시 세션에 저장 (이름 주의!)
                                            st.session_state.final_image = Image.alpha_composite(base_image, watermark_layer)
                                            st.session_state.synthesis_count = 2 # 재합성 완료 상태
                                            st.session_state.show_confirm_redo = False # 확인창 닫기
                                            
                                            st.rerun() # 화면 갱신
                                        else:
                                            st.error("AI가 이미지를 생성하지 못했습니다. 다시 시도해 주세요.")

                                    except Exception as e:
                                        st.error(f"재합성 중 오류 발생: {e}")

                # --- [마무리: 다른 사진 합성하기 (확인창 포함)] ---
                if st.session_state.synthesis_count >= 1:
                    st.write("")
                    # 초기화 확인창이 떠있지 않을 때만 버튼 노출
                    if not st.session_state.show_confirm_reset:
                        if st.button("📸 다른 사진으로 새로 합성하기"):
                            st.session_state.show_confirm_reset = True
                            st.rerun()
                    
                    # 초기화 확인창 활성화 시
                    else:
                        st.warning("⚠️ 정말 새로 시작하시겠어요? 지금까지의 작업은 저장되지 않습니다.")
                        col3, col4 = st.columns(2)
                        with col3:
                            if st.button("✅ 네, 새로 시작할게요"):
                                st.session_state.show_confirm_reset = False
                                reset_app() # 초기화 함수 호출
                        with col4:
                            if st.button("❌ 아니오"):
                                st.session_state.show_confirm_reset = False
                                st.rerun()

                st.markdown("---")
                st.success("✅ 모든 과정이 완료되었습니다! 화면을 캡쳐해 주세요.")

        else:
            st.error("잔여 횟수가 0입니다. 충전이 필요합니다.")
    else:
        st.error("잘못된 키입니다.")
else:
    st.info("좌측 상단의 ' >> '를 눌러서 키를 입력해주세요.")